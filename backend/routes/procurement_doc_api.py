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
from routes.utils import login_required

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
    """设置/调整项目分包数量（包固定不变，仅在第一轮且无包中标前可改）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    if session.get("role", "") == "agency":
        return jsonify({"ok": False, "error": "代理机构不能设置分包"}), 403
    data = request.get_json(silent=True) or {}
    count = max(1, min(50, int(data.get("count") or 1)))

    if (project.round or 1) > 1:
        return jsonify({"ok": False, "error": "项目已进入第二轮及以后，包数量不可调整"}), 400
    won = db.session.execute(
        db.select(Package).filter_by(project_id=pid).where(Package.status != "进行中")
    ).first()
    if won:
        return jsonify({"ok": False, "error": "已有包中标/签约，包数量不可调整"}), 400

    rnd = _current_round(project)   # 第一轮（无则建）
    existing = db.session.execute(
        db.select(Package).filter_by(project_id=pid)
    ).scalars().all()
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
    db.session.commit()
    return jsonify({"ok": True, "data": {"package_count": count}})


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
    db.session.commit()
    data_out = project.to_dict()
    data_out["package_count"] = db.session.execute(
        db.select(db.func.count()).select_from(Package).filter_by(project_id=pid)
    ).scalar_one()
    return jsonify({"ok": True, "data": data_out})


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

    f = request.files.get("file")
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
    return send_file(path, as_attachment=False, download_name=att.original_name)


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
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})

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
    return jsonify({"ok": True, "data": _aigen.get(pid, {
        "running": False, "ok": None, "msg": ""})})
