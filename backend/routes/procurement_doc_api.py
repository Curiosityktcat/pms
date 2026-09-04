import datetime
import hashlib
import os
import uuid
from flask import Blueprint, request, session, jsonify, send_file, current_app
from models import db
from models.project import Project
from models.agency import Agency
from models.procurement_doc_attachment import ProcurementDocAttachment
from models.procurement_demand import ProcurementDemand
from models.package import Package
from models.procurement_round import ProcurementRound
from models.round_package import RoundPackage
from services import approval_log as alog
from routes.utils import login_required
from services import upload_relay
from services.dept_scope import assert_can_view_project

bp = Blueprint("procurement_doc", __name__, url_prefix="/api/projects")

# 采购文件编制阶段上传附件的存储根目录
UPLOAD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "procurement_doc")
)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

ALLOWED_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".zip", ".rar",
}


def _check_project_access(project):
    """返回 (ok, error_json, status)；校验项目可用且当前用户有权操作。"""
    if not project:
        return False, {"ok": False, "error": "项目不存在"}, 404
    assert_can_view_project(project.id)
    if project.is_draft:
        return False, {"ok": False, "error": "草稿项目无法生成采购文件"}, 400
    if not project.agency_code:
        return False, {"ok": False, "error": "该项目不走代理机构"}, 400
    role = session.get("role", "")
    if role == "officer" and project.officer != session.get("display_name", ""):
        return False, {"ok": False, "error": "无权操作该项目"}, 403
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return False, {"ok": False, "error": "无权操作该项目"}, 403
    return True, None, 200


def _agency_name(project, override=""):
    if override:
        return override.strip()
    a = db.session.execute(
        db.select(Agency).filter_by(code=project.agency_code)
    ).scalar_one_or_none()
    return a.name if a else project.agency_code


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _doc_confirm_date_cn(project, rnd=None):
    """经办人确认采购文件的当天 → 中文「YYYY年M月D日」，供内容确认表/封面填日期。"""
    raw = (getattr(rnd, "doc_confirmed_at", "") if rnd else "") or (project.doc_confirmed_at or "")
    if not raw:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(raw)
        return f"{dt.year}年{dt.month}月{dt.day}日"
    except Exception:
        return ""


def _current_round(project, create=True):
    """取项目当前（最新）轮次；不存在时按需创建第一轮。"""
    r = db.session.execute(
        db.select(ProcurementRound)
        .filter_by(project_id=project.id)
        .order_by(ProcurementRound.round_number.desc())
    ).scalars().first()
    if r is None and create:
        r = ProcurementRound(project_id=project.id, round_number=1,
                             status="进行中", created_at=_now())
        db.session.add(r)
        db.session.flush()
        project.round = 1
    return r


def _ensure_packages(project, current_round, count):
    """首次按「包数量」生成包（包固定不变，已存在则忽略 count）。"""
    existing = db.session.execute(
        db.select(Package).filter_by(project_id=project.id)
    ).scalars().all()
    if existing:
        return existing
    count = max(1, int(count or 1))
    pkgs = []
    for i in range(1, count + 1):
        pk = Package(project_id=project.id, package_no=i,
                     status="进行中", created_at=_now())
        db.session.add(pk)
        pkgs.append(pk)
    db.session.flush()
    # 把包关联到当前轮次
    for pk in pkgs:
        db.session.add(RoundPackage(round_id=current_round.id, package_id=pk.id, result="待定"))
    return pkgs


@bp.route("/<int:pid>/packages", methods=["POST"])
@login_required
def set_package_count(pid):
    """设置/调整项目分包数量（无包中标/签约、本轮采购结果未确认前均可调整）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    if session.get("role", "") == "agency":
        return jsonify({"ok": False, "error": "代理机构不能设置分包"}), 403
    data = request.get_json(silent=True) or {}
    count = max(1, min(50, int(data.get("count") or 1)))

    # 2026-08-12 放开「进入第二轮就不可调整」：改成只要**没有任何包已中标/签约**就能改。
    # 起因：分包填错（两个包做成一个包）而首轮已流标进入第二轮时，采购结果确认函的包是
    # 「按当前轮次自动带出、不可增删」的，代理只能填出错误的包数 → 整个项目卡死，
    # 界面上谁也改不了，只能改库。
    won = db.session.execute(
        db.select(Package).filter_by(project_id=pid).where(Package.status != "进行中")
    ).first()
    if won:
        return jsonify({"ok": False, "error": "已有包中标/签约，包数量不可调整"}), 400

    rnd = _current_round(project)   # 当前轮次（无则建第一轮）

    # 本轮采购结果已确认则不能再动包（结果已生效，改包会让确认函对不上）
    from models.procurement_result import ProcurementResult
    done_res = db.session.execute(
        db.select(ProcurementResult.id)
        .filter_by(project_id=pid, round_number=rnd.round_number, status="已确认")
    ).first()
    if done_res:
        return jsonify({"ok": False, "error": "本轮采购结果已确认，包数量不可调整"}), 400

    existing = db.session.execute(
        db.select(Package).filter_by(project_id=pid).order_by(Package.package_no)
    ).scalars().all()

    if (project.round or 1) <= 1:
        # 第一轮：没有历史包袱，沿用原来的「删了重建」，包号从 1 连续
        ex_ids = [p.id for p in existing]
        if ex_ids:
            db.session.execute(db.delete(RoundPackage).where(RoundPackage.package_id.in_(ex_ids)))
            db.session.execute(db.delete(Package).where(Package.id.in_(ex_ids)))
            db.session.flush()
        for i in range(1, count + 1):
            pk = Package(project_id=pid, package_no=i, status="进行中", created_at=_now())
            db.session.add(pk)
            db.session.flush()
            db.session.add(RoundPackage(round_id=rnd.id, package_id=pk.id, result="待定"))
    else:
        # 第二轮及以后：**增量调整**，绝不删已有包（它们身上挂着历史轮次记录）
        round_ids = [r.id for r in db.session.execute(
            db.select(ProcurementRound).filter_by(project_id=pid)
        ).scalars().all()]
        cur_n = len(existing)
        if count > cur_n:
            next_no = (existing[-1].package_no if existing else 0) + 1
            for _ in range(count - cur_n):
                pk = Package(project_id=pid, package_no=next_no, status="进行中", created_at=_now())
                db.session.add(pk)
                db.session.flush()
                # 补挂到该项目所有轮次（含已结束轮），保证历史与归档里包数一致
                for rid in round_ids:
                    db.session.add(RoundPackage(round_id=rid, package_id=pk.id, result="待定"))
                next_no += 1
        elif count < cur_n:
            drop = [p.id for p in existing[count:]]
            db.session.execute(db.delete(RoundPackage).where(RoundPackage.package_id.in_(drop)))
            db.session.execute(db.delete(Package).where(Package.id.in_(drop)))

    db.session.commit()
    # 本轮已有结果草稿/待确认 → 包变了，提醒回去核对确认函
    warn = ""
    draft_res = db.session.execute(
        db.select(ProcurementResult.id)
        .filter_by(project_id=pid, round_number=rnd.round_number)
    ).first()
    if draft_res:
        warn = "本轮采购结果已有草稿，包数量已变，请回到「采购结果确认函」重新核对包信息"
    return jsonify({"ok": True, "data": {"package_count": count, "warn": warn}})


@bp.route("/<int:pid>/rounds", methods=["GET"])
@login_required
def list_rounds(pid):
    """返回项目的轮次、包、以及每轮的包结果，供前端「第几次」弹窗使用。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    rounds = db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=pid)
        .order_by(ProcurementRound.round_number)
    ).scalars().all()
    packages = db.session.execute(
        db.select(Package).filter_by(project_id=pid).order_by(Package.package_no)
    ).scalars().all()
    rps = db.session.execute(
        db.select(RoundPackage).join(ProcurementRound,
                                     RoundPackage.round_id == ProcurementRound.id)
        .where(ProcurementRound.project_id == pid)
    ).scalars().all()
    return jsonify({
        "ok": True,
        "data": {
            "rounds": [r.to_dict() for r in rounds],
            "packages": [p.to_dict() for p in packages],
            "round_packages": [rp.to_dict() for rp in rps],
            "current_round": rounds[-1].round_number if rounds else 0,
        },
    })


# 确认历史各环节配置：确认位字段 / 附件 kind / 「确认后下一步」阶段（可撤回的判据）
_CONFIRM_HISTORY = {
    "demand": {
        "flag": "demand_confirmed", "by": "demand_confirmed_by", "at": "demand_confirmed_at",
        "att_kind": "demand", "next_stages": ("doc_confirm",),
    },
    "doc": {
        "flag": "doc_confirmed", "by": "doc_confirmed_by", "at": "doc_confirmed_at",
        # 文件确认后下一步：代理轨道=发公告(announce)，简精轨道=采购结果(result)
        "att_kind": "doc", "next_stages": ("announce", "result"),
    },
}


def _confirmation_history(kind):
    """按轮次列出某确认环节（demand/doc）每一次「已确认」的快照。

    每条 = 某项目某轮的确认，确认人/时间取自该轮 ProcurementRound 真源、附件取该轮，
    都是「那次确认当时」的内容，不随项目进下一轮或后续阶段而变（镜像位只反映最新轮）。
    某轮未上传新附件（无修改沿用上次）时文件回落到之前最近一轮；
    可撤回 = 该轮是当前轮且刚过本环节、尚未进入后续步骤（避免破坏已进行的后续）。
    """
    cfg = _CONFIRM_HISTORY[kind]
    from services import project as svc
    rows = svc.list_projects(
        role=session["role"],
        agency_code=session.get("agency_code", ""),
        officer=session.get("display_name", ""),
        show_deleted=False,
        dept_code=session.get("dept_code", ""),
    )
    proj_meta = {r["id"]: r for r in rows if r.get("agency_code") and not r.get("is_draft")}
    ids = list(proj_meta.keys())
    if not ids:
        return jsonify({"ok": True, "data": []})

    flag_col = getattr(ProcurementRound, cfg["flag"])
    rounds = db.session.execute(
        db.select(ProcurementRound)
        .where(ProcurementRound.project_id.in_(ids))
        .where(flag_col == 1)
        .order_by(ProcurementRound.project_id, ProcurementRound.round_number)
    ).scalars().all()

    # 附件按 (project_id, round_number) 归组——取该轮当时上传的文件
    att_map = {}
    for a in db.session.execute(
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id.in_(ids))
        .where(ProcurementDocAttachment.kind == cfg["att_kind"])
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all():
        att_map.setdefault((a.project_id, a.round_number or 1), []).append(a)

    # 包数量为项目级（第一轮固定），各轮展示一致
    pkg_counts = dict(db.session.execute(
        db.select(Package.project_id, db.func.count())
        .where(Package.project_id.in_(ids))
        .group_by(Package.project_id)
    ).all())

    # 各项目「有附件的轮次」升序：某轮未上传（无修改沿用上一轮）时回落
    files_rounds = {}
    for (pid, r), flist in att_map.items():
        if flist:
            files_rounds.setdefault(pid, []).append(r)
    for v in files_rounds.values():
        v.sort()

    from services.project_progress import stage_map
    stages = stage_map(ids)

    out = []
    for rnd in rounds:
        pid = rnd.project_id
        meta = proj_meta.get(pid, {})
        rn = rnd.round_number or 1
        own = att_map.get((pid, rn), [])
        if own:
            files_round, flist = rn, own
        else:
            prior = [r for r in files_rounds.get(pid, []) if r <= rn]
            files_round = prior[-1] if prior else rn
            flist = att_map.get((pid, files_round), [])
        st = stages.get(pid, {})
        out.append({
            "project_id": pid,
            "project_name": meta.get("name", ""),
            "number": meta.get("number", ""),
            "agency_name": meta.get("agency_name", "") or meta.get("agency_code", ""),
            "round_number": rn,
            "package_count": pkg_counts.get(pid, 0),
            "confirmed_by": getattr(rnd, cfg["by"]) or "",
            "confirmed_at": getattr(rnd, cfg["at"]) or "",
            "files": [a.to_dict() for a in flist],
            "files_round": files_round,            # 文件实际所属轮次（无修改时沿用上一轮）
            "files_inherited": files_round != rn,  # 本轮未上传新文件、沿用上一轮
            "revocable": st.get("current_round") == rn and st.get("current_stage") in cfg["next_stages"],
        })
    return jsonify({"ok": True, "data": out})


@bp.route("/demand-confirmations", methods=["GET"])
@login_required
def list_demand_confirmations():
    """采购需求确认(5.1)历史：按轮次列出每一次已确认的需求快照。"""
    return _confirmation_history("demand")


@bp.route("/doc-confirmations", methods=["GET"])
@login_required
def list_doc_confirmations():
    """采购文件确认(5.2)历史：按轮次列出每一次已确认的采购文件快照。"""
    return _confirmation_history("doc")


@bp.route("/<int:pid>/bid-cover", methods=["POST"])
@login_required
def generate_bid_cover(pid):
    """按模板生成招标文件封面 Word。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    _rnum = int(data.get("round_number") or project.round or 1)
    _rnd = _current_round(project, create=False)
    # 封面编制时间 = 经办人确认采购文件当天（前端如显式传入则尊重其值）
    compile_date = (data.get("compile_date") or "").strip() or _doc_confirm_date_cn(project, _rnd)
    from services.bid_cover_word import generate
    try:
        buf, filename = generate(
            project,
            _agency_name(project, data.get("agency_name", "")),
            compile_date=compile_date,
            round_number=_rnum,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ── 两步确认：采购需求确认(demand) / 采购文件确认(doc) ──────────────────
_CONFIRM_FIELDS = {
    "demand": ("demand_confirmed", "demand_confirmed_by", "demand_confirmed_at"),
    "doc":    ("doc_confirmed",    "doc_confirmed_by",    "doc_confirmed_at"),
}


@bp.route("/<int:pid>/doc-confirm", methods=["POST"])
@login_required
def set_doc_confirm(pid):
    """标记/撤销 采购需求确认 或 采购文件确认（记录确认人与时间）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "")
    if kind not in _CONFIRM_FIELDS:
        return jsonify({"ok": False, "error": "确认类型无效"}), 400
    # 确认由采购人方（经办人/助理/负责人）审核，代理机构只能上传不能确认
    if session.get("role", "") == "agency":
        return jsonify({"ok": False, "error": "代理机构只能上传文件，确认由经办人审核"}), 403
    confirmed = bool(data.get("confirmed", True))

    rnd = _current_round(project)        # 当前轮次（首次自动建第一轮）
    by = session.get("display_name", "") if confirmed else ""
    at = _now() if confirmed else ""

    # 采购需求确认：首次确认时按「包数量」生成包（包固定不变）
    if kind == "demand" and confirmed:
        _ensure_packages(project, rnd, data.get("package_count"))

    f_flag, f_by, f_at = _CONFIRM_FIELDS[kind]
    # 同时写入「轮次」(真源) 与「项目」(过渡期镜像，兼容现有页面)
    setattr(rnd, f_flag, 1 if confirmed else 0)
    setattr(rnd, f_by, by)
    setattr(rnd, f_at, at)
    setattr(project, f_flag, 1 if confirmed else 0)
    setattr(project, f_by, by)
    setattr(project, f_at, at)
    if confirmed:
        # 确认即视为本次往返结束，清掉挂在轮次上的驳回提示（历史仍在 approval_logs）
        setattr(rnd, f"{kind}_reject_reason", "")
    alog.log(pid, kind, "confirm" if confirmed else "revoke",
             round_number=rnd.round_number or 1)
    db.session.commit()
    data_out = project.to_dict()
    data_out["package_count"] = db.session.execute(
        db.select(db.func.count()).select_from(Package).filter_by(project_id=pid)
    ).scalar_one()
    # 采购文件确认完成 → 自动把「采购文件确认函」推到 rd-web 采购项目审批盖章
    push_info = {}
    if kind == "doc" and confirmed:
        from routes.rdweb_approval_api import auto_push_on_confirm
        push_info = auto_push_on_confirm(project, "doc_confirm", rnd.round_number or 1)
    return jsonify({"ok": True, "data": data_out, "rdweb_push": push_info})


@bp.route("/<int:pid>/doc-reject", methods=["POST"])
@login_required
def reject_doc(pid):
    """驳回采购需求(5.1) / 采购文件(5.2)：打回代理机构修改，必须写明原因。

    与「撤销确认」不同——撤销只是把标记抹掉，驳回会留下原因并计次，
    代理机构侧能直接看到要改什么，改完重新上传即进入下一次往返。
    """
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "")
    if kind not in _CONFIRM_FIELDS:
        return jsonify({"ok": False, "error": "确认类型无效"}), 400
    if session.get("role", "") == "agency":
        return jsonify({"ok": False, "error": "驳回由采购人方操作，代理机构只能修改后重新提交"}), 403
    issues = alog.norm_issues(data.get("issues"))
    reason = (data.get("reason") or "").strip()
    # 问题清单是主，原因是摘要：逐条填了问题就不必再写一遍原因，
    # 系统按分类拼一段给代理机构看。两样都空才拦。
    if not reason and issues:
        reason = "；".join(
            f"[{alog.ISSUE_LABELS.get(i['category'], i['category'])}] {i['text']}"
            for i in issues)
    if not reason:
        return jsonify({"ok": False, "error": "请填写驳回原因，或逐条列出问题"}), 400

    rnd = _current_round(project)
    f_flag, f_by, f_at = _CONFIRM_FIELDS[kind]
    # 驳回即撤下确认标记，回到"待代理机构修改"
    setattr(rnd, f_flag, 0)
    setattr(rnd, f_by, "")
    setattr(rnd, f_at, "")
    setattr(project, f_flag, 0)
    setattr(project, f_by, "")
    setattr(project, f_at, "")

    cnt = int(getattr(rnd, f"{kind}_reject_count", 0) or 0) + 1
    setattr(rnd, f"{kind}_reject_reason", reason)
    setattr(rnd, f"{kind}_reject_count", cnt)
    setattr(rnd, f"{kind}_rejected_by", session.get("display_name", ""))
    setattr(rnd, f"{kind}_rejected_at", _now())
    alog.log(pid, kind, "reject", round_number=rnd.round_number or 1,
             reason=reason, issues=issues)
    db.session.commit()
    label = "采购需求" if kind == "demand" else "采购文件"
    n_ded = sum(1 for i in issues if i["category"] in alog.DEDUCT_KEYS)
    tail = f"，其中 {n_ded} 条属代理机构文件问题，将计入服务质量考核" if n_ded else ""
    return jsonify({"ok": True,
                    "message": f"已驳回{label}（第{cnt}次），代理机构可修改后重新提交{tail}",
                    "data": rnd.to_dict()})


@bp.route("/<int:pid>/doc-events", methods=["GET"])
@login_required
def doc_events_timeline(pid):
    """采购文件的上传/删除时间线（含已删除的版本，考核算时效就看这个）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    from services import doc_events
    return jsonify({"ok": True,
                    "data": doc_events.timeline(pid, request.args.get("kind") or None)})


@bp.route("/reject-issue-categories", methods=["GET"])
@login_required
def reject_issue_categories():
    """驳回问题的分类表，前端下拉直接用（哪一类扣分也一并给出）。"""
    return jsonify({"ok": True, "data": alog.ISSUE_CATEGORIES})


@bp.route("/<int:pid>/approval-logs", methods=["GET"])
@login_required
def approval_logs(pid):
    """本项目的审批往返记录（可按 node 过滤），前端展示驳回历史时间线。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    return jsonify({"ok": True,
                    "data": alog.list_for_project(pid, request.args.get("node") or None)})


@bp.route("/<int:pid>/doc-contact", methods=["POST"])
@login_required
def save_doc_contact(pid):
    """保存内容确认表所需的代理机构联系人及联系方式（代理机构在系统填写）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    data = request.get_json(silent=True) or {}
    contact = (data.get("contact_person") or "").strip()
    phone = (data.get("contact_phone") or "").strip()
    rnd = _current_round(project)               # 联系人按轮次保存
    rnd.doc_agency_contact = contact
    rnd.doc_agency_phone = phone
    project.doc_agency_contact = contact         # 镜像项目位（兼容）
    project.doc_agency_phone = phone
    db.session.commit()
    return jsonify({"ok": True, "data": project.to_dict()})


@bp.route("/<int:pid>/content-confirm-word", methods=["POST"])
@login_required
def generate_content_confirm_word(pid):
    """生成《院内竞选文件内容确认表》Word（须经办人确认采购文件后）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    rnd = _current_round(project, create=False)
    rno = rnd.round_number if rnd else 1
    # 工作流：代理上传 → 经办人确认 → 确认后哈希定稿并自动填入内容确认表
    if not (rnd.doc_confirmed if rnd else project.doc_confirmed):
        return jsonify({"ok": False, "error": "采购文件尚未确认，请先由经办人确认后再生成内容确认表"}), 400

    data = request.get_json(silent=True) or {}
    # 收集本轮采购文件(doc)附件的 SHA256，填入内容确认表
    docs = db.session.execute(
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id == pid)
        .where(ProcurementDocAttachment.kind == "doc")
        .where(ProcurementDocAttachment.round_number == rno)
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()
    file_hashes = [(d.original_name, d.sha256) for d in docs if d.sha256]

    # 联系人优先取请求覆盖值，否则用本轮（回落项目）保存的值
    _rc = (rnd.doc_agency_contact if rnd else "") or project.doc_agency_contact or ""
    _rp = (rnd.doc_agency_phone if rnd else "") or project.doc_agency_phone or ""
    contact_person = (data.get("contact_person") or _rc).strip()
    contact_phone = (data.get("contact_phone") or _rp).strip()

    from services.content_confirm_word import generate
    try:
        buf, filename = generate(
            project,
            _agency_name(project, data.get("agency_name", "")),
            file_hashes=file_hashes,
            contact_person=contact_person,
            contact_phone=contact_phone,
            confirm_date=_doc_confirm_date_cn(project, rnd),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ── AI 编制建议（Phase 2）──────────────────────────────────────────────
@bp.route("/<int:pid>/ai-review", methods=["POST"])
@login_required
def ai_review_doc(pid):
    """调用大模型，对该项目采购需求给出编制意见和建议（只读建议，不改文档、不定稿）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    # 取该项目最新版采购需求
    demand = db.session.execute(
        db.select(ProcurementDemand)
        .filter_by(project_id=pid)
        .order_by(ProcurementDemand.version.desc(), ProcurementDemand.id.desc())
    ).scalars().first()
    if demand is None:
        return jsonify({"ok": False,
                        "error": "未找到该项目的采购需求数据，请先在采购需求环节填写后再生成建议"}), 400

    # 代理机构：余额不足则拦截（内部账号不计费）
    role = session.get("role", "")
    agency_code = session.get("agency_code", "") if role == "agency" else ""
    if agency_code:
        from services.billing import get_balance
        bal = get_balance(agency_code)
        if bal is not None and bal <= 0:
            return jsonify({"ok": False,
                            "error": "AI 余额不足，请联系采购部充值后再使用"}), 402

    from services.procurement_doc_ai import review, current_model_name
    usage_ctx = {
        "username": session.get("user", ""),
        "display_name": session.get("display_name", ""),
        "feature": "ai-review",
        "agency_code": agency_code,
    }
    try:
        suggestions = review(project, demand, usage_ctx=usage_ctx)
    except Exception as e:
        return jsonify({"ok": False, "error": f"AI 生成失败：{e}"}), 502
    data = {"suggestions": suggestions, "model": current_model_name()}
    if agency_code:  # 代理机构回传扣费后余额
        from services.billing import get_balance
        data["balance"] = round(get_balance(agency_code) or 0, 2)
    return jsonify({"ok": True, "data": data})


# ── 上传附件（采购需求确认 等）─────────────────────────────────────────
def _attach_dir(pid: int) -> str:
    d = os.path.join(UPLOAD_ROOT, str(pid))
    os.makedirs(d, exist_ok=True)
    return d


def _norm_kind(raw):
    return raw if raw in ("demand", "doc") else "demand"


def _kind_confirmed(project, kind):
    """该确认环节本轮是否已确认（已确认则锁定，不允许增删文件）。"""
    rnd = _current_round(project, create=False)
    flag = "doc_confirmed" if kind == "doc" else "demand_confirmed"
    if rnd is not None:
        return bool(getattr(rnd, flag, 0))
    return bool(getattr(project, flag, 0))  # 无轮次时回落到项目位（兼容）


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@bp.route("/<int:pid>/doc-attachments", methods=["GET"])
@login_required
def list_doc_attachments(pid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    kind = _norm_kind(request.args.get("kind", "demand"))
    # 指定轮次则查历史轮（供「已确认」历史只读查看）；不传默认当前轮
    rno = request.args.get("round_number", type=int)
    if rno is None:
        rnd = _current_round(project, create=False)
        rno = rnd.round_number if rnd else 1
    rows = db.session.execute(
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id == pid)
        .where(ProcurementDocAttachment.kind == kind)
        .where(ProcurementDocAttachment.round_number == rno)
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:pid>/doc-attachments", methods=["POST"])
@login_required
def upload_doc_attachment(pid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    kind = _norm_kind(request.args.get("kind", "demand"))
    if _kind_confirmed(project, kind):
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤销确认"}), 400

    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False, "error": f"不支持的文件格式：{ext}，支持 PDF/Word/Excel/图片/压缩包"}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(_attach_dir(pid), saved_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    sha256 = _sha256_of(save_path)

    rnd = _current_round(project)  # 归属当前轮次
    att = ProcurementDocAttachment(
        project_id=pid,
        kind=kind,
        round_number=rnd.round_number if rnd else 1,
        original_name=f.filename,
        saved_name=saved_name,
        file_size=file_size,
        sha256=sha256,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=datetime.datetime.now().isoformat(timespec="seconds"),
    )
    db.session.add(att)
    db.session.flush()                      # 先拿到 id，留痕要指向它
    from services import doc_events
    doc_events.record(att, "upload", when=att.uploaded_at)
    db.session.commit()
    return jsonify({"ok": True, "message": "上传成功", "data": att.to_dict()}), 201


@bp.route("/<int:pid>/doc-attachments/<int:aid>", methods=["GET"])
@login_required
def download_doc_attachment(pid, aid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_attach_dir(pid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


@bp.route("/<int:pid>/doc-attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview_doc_attachment(pid, aid):
    """内联预览（PDF/图片直接在浏览器渲染，docx/xlsx 由前端渲染）"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_attach_dir(pid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    from services.office_convert import send_preview
    return send_preview(path, att.original_name)


@bp.route("/<int:pid>/doc-attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete_doc_attachment(pid, aid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if _kind_confirmed(project, att.kind):
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤销确认"}), 400
    try:
        path = os.path.join(_attach_dir(pid), att.saved_name)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    # 文件可以删，「谁在几号交过这一版」的留痕不能删——考核算编制时效靠它，
    # 删干净了代理机构就得为自己没犯的拖延背锅（2026-09-04 心脏脉冲项目的教训）。
    from services import doc_events
    doc_events.record(att, "delete")
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除（上传记录保留在时间线里）"})


# ══════════════════════════════════════════════════════════════════
# 从项目池挑选采购需求文件
# 项目池（rd-web 抓来的审签表）里混有医院内部文件，全量带入会连同内部文件
# 一起发给代理机构，所以立项时不再自动复制；改由经办人在此按需勾选导入。
# 仅采购人方（经办人/助理/负责人）可用，代理机构不得访问项目池。
# ══════════════════════════════════════════════════════════════════
_POOL_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "project_distribution")
)


def _pool_atts(pid):
    """该项目关联的项目池附件（审签表不列——那是流程表单，不是采购需求）。"""
    from models.project_distribution import (
        ProjectDistribution, ProjectDistributionAttachment,
    )
    dists = db.session.execute(
        db.select(ProjectDistribution).filter_by(project_id=pid)
    ).scalars().all()
    out = []
    for d in dists:
        rows = db.session.execute(
            db.select(ProjectDistributionAttachment)
            .filter_by(distribution_id=d.id)
            .order_by(ProjectDistributionAttachment.id)
        ).scalars().all()
        out += [(d, a) for a in rows if (a.category or "") != "审签表"]
    return out


def _pool_allowed():
    return session.get("role", "") in ("officer", "assistant", "pd_assistant", "leader")


@bp.route("/<int:pid>/pool-attachments", methods=["GET"])
@login_required
def list_pool_attachments(pid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    if not _pool_allowed():
        return jsonify({"ok": False, "error": "项目池不对代理机构开放"}), 403
    rnd = _current_round(project, create=False)
    rno = rnd.round_number if rnd else 1
    # 已导入过的（同名）标记出来，避免经办人重复导入
    imported = {
        r.original_name for r in db.session.execute(
            db.select(ProcurementDocAttachment)
            .where(ProcurementDocAttachment.project_id == pid)
            .where(ProcurementDocAttachment.kind == "demand")
            .where(ProcurementDocAttachment.round_number == rno)
        ).scalars().all()
    }
    data = []
    for d, a in _pool_atts(pid):
        item = a.to_dict()
        item["serial_no"] = d.serial_no or ""
        item["exists"] = os.path.exists(
            os.path.join(_POOL_ROOT, str(d.id), a.saved_name or ""))
        item["imported"] = a.original_name in imported
        data.append(item)
    return jsonify({"ok": True, "data": data})


@bp.route("/<int:pid>/pool-attachments/import", methods=["POST"])
@login_required
def import_pool_attachments(pid):
    """把勾选的项目池附件复制成本轮采购需求附件（kind='demand'）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    if not _pool_allowed():
        return jsonify({"ok": False, "error": "项目池不对代理机构开放"}), 403
    if _kind_confirmed(project, "demand"):
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤销确认"}), 400
    ids = set((request.get_json(silent=True) or {}).get("ids") or [])
    if not ids:
        return jsonify({"ok": False, "error": "未选择文件"}), 400

    import shutil
    rnd = _current_round(project)
    rno = rnd.round_number if rnd else 1
    dest_dir = _attach_dir(pid)
    now = _now()
    added = 0
    for d, a in _pool_atts(pid):
        if a.id not in ids:
            continue
        src = os.path.join(_POOL_ROOT, str(d.id), a.saved_name or "")
        if not a.saved_name or not os.path.exists(src):
            continue
        ext = os.path.splitext(a.original_name or a.saved_name or "")[1]
        saved_name = f"{uuid.uuid4().hex}{ext}"
        dest = os.path.join(dest_dir, saved_name)
        shutil.copy(src, dest)
        db.session.add(ProcurementDocAttachment(
            project_id=pid, kind="demand", round_number=rno,
            original_name=a.original_name, saved_name=saved_name,
            file_size=os.path.getsize(dest), sha256=_sha256_of(dest),
            uploaded_by=session.get("display_name", ""), uploaded_at=now,
        ))
        added += 1
    if not added:
        return jsonify({"ok": False, "error": "所选文件不存在或已丢失"}), 400
    db.session.commit()
    return jsonify({"ok": True, "message": f"已从项目池导入 {added} 个文件"})


# ══════════════════════════════════════════════════════════════════
# AI 一键生成采购文件定稿：选初稿/模板 + 采购需求附件 → DeepSeek 段落级修订
# （后台线程执行，前端轮询状态；按 token 计费，代理机构余额拦截）
# ══════════════════════════════════════════════════════════════════
import threading as _threading

_aigen: dict = {}
_aigen_lock = _threading.Lock()


@bp.route("/<int:pid>/ai-generate-doc", methods=["POST"])
@login_required
def ai_generate_doc(pid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    if _kind_confirmed(project, "doc"):
        return jsonify({"ok": False, "error": "采购文件已确认，如需重新生成请先撤销确认"}), 400

    data = request.get_json(force=True) or {}
    draft_id = data.get("draft_attachment_id")
    demand_id = data.get("demand_attachment_id")

    def _get_att(aid):
        att = db.session.get(ProcurementDocAttachment, aid or 0)
        if att is None or att.project_id != pid:
            return None
        return att

    draft_att, demand_att = _get_att(draft_id), _get_att(demand_id)
    if not draft_att or not demand_att:
        return jsonify({"ok": False, "error": "请选择初稿/模板文件和采购需求文件"}), 400
    for att, label in ((draft_att, "初稿/模板"), (demand_att, "采购需求")):
        if os.path.splitext(att.saved_name)[1].lower() not in (".doc", ".docx"):
            return jsonify({"ok": False,
                            "error": f"{label}仅支持 Word（doc/docx）格式"}), 400

    role = session.get("role", "")
    agency_code = session.get("agency_code", "") if role == "agency" else ""
    if agency_code:
        from services.billing import get_balance
        bal = get_balance(agency_code)
        if bal is not None and bal <= 0:
            return jsonify({"ok": False,
                            "error": "AI 余额不足，请联系采购部充值后再使用"}), 402

    with _aigen_lock:
        if _aigen.get(pid, {}).get("running"):
            return jsonify({"ok": False, "error": "该项目正在生成中，请稍候"}), 429
        _aigen[pid] = {"running": True, "ok": None, "msg": "AI 生成中（约 2~5 分钟）…"}

    app = current_app._get_current_object()
    d = _attach_dir(pid)
    draft_path = os.path.join(d, draft_att.saved_name)
    demand_path = os.path.join(d, demand_att.saved_name)
    username = session.get("user", "")
    display = session.get("display_name", "")
    rnd = _current_round(project)
    rno = rnd.round_number if rnd else 1
    proj_name = project.name or ""

    def _worker():
        try:
            from services.procurement_doc_gen import generate_final_doc
            saved_name = f"{uuid.uuid4().hex}.docx"
            out_path = os.path.join(d, saved_name)
            summary, applied, usage = None, None, None
            with app.app_context():
                summary, applied, usage = generate_final_doc(
                    draft_path, demand_path, out_path)
                att = ProcurementDocAttachment(
                    project_id=pid,
                    kind="doc",
                    round_number=rno,
                    original_name=f"{proj_name}（AI定稿）.docx",
                    saved_name=saved_name,
                    file_size=os.path.getsize(out_path),
                    sha256=_sha256_of(out_path),
                    uploaded_by=f"{display}（AI生成）",
                    uploaded_at=datetime.datetime.now().isoformat(timespec="seconds"),
                )
                db.session.add(att)
                db.session.flush()
                from services import doc_events
                doc_events.record(att, "upload", when=att.uploaded_at,
                                  operator_name=att.uploaded_by)
                db.session.commit()
                from services import llm_usage
                llm_usage.record(username, display, "采购文件AI生成",
                                 "deepseek-v4-flash", usage,
                                 agency_code=agency_code)
            with _aigen_lock:
                _aigen[pid] = {"running": False, "ok": True,
                               "msg": f"生成完成，共 {len(applied)} 处修订",
                               "summary": summary, "edits": applied,
                               "usage": usage}
        except Exception as e:  # noqa: BLE001
            with _aigen_lock:
                _aigen[pid] = {"running": False, "ok": False,
                               "msg": f"生成失败：{str(e)[:300]}"}

    _threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始生成"})


@bp.route("/<int:pid>/ai-generate-doc/status")
@login_required
def ai_generate_doc_status(pid):
    assert_can_view_project(pid)
    return jsonify({"ok": True, "data": _aigen.get(pid, {
        "running": False, "ok": None, "msg": ""})})
