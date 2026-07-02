import os
import uuid
import hashlib
from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
import json
from models import db
from models.procurement_result import ProcurementResult
from models.procurement_doc_attachment import ProcurementDocAttachment
from models.project import Project
from models.package import Package
from models.procurement_round import ProcurementRound
from models.round_package import RoundPackage
from routes.utils import login_required

bp = Blueprint("procurement_result", __name__, url_prefix="/api/procurement-results")

# 招单价项目：成交结果「单价详见附件」上传目录
UPLOAD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "procurement_result")
)
os.makedirs(UPLOAD_ROOT, exist_ok=True)
ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg", ".zip", ".rar"}


def _price_attach_dir(pid: int) -> str:
    d = os.path.join(UPLOAD_ROOT, str(pid))
    os.makedirs(d, exist_ok=True)
    return d


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _can_confirm() -> bool:
    """确认/撤回采购结果仅限采购人方；代理机构只能编辑内容。"""
    return session.get("role", "") in ("officer", "assistant", "leader")


def _project_agency(project_id) -> str:
    p = db.session.get(Project, project_id)
    return p.agency_code if p else ""


def _current_round_number(project_id):
    """项目当前（最新）轮次号，无则 0。"""
    n = db.session.execute(
        db.select(db.func.max(ProcurementRound.round_number)).filter_by(project_id=project_id)
    ).scalar()
    return n or 0


def _apply_result_to_cycle(result):
    """采购结果确认后驱动按包循环：

    成交包 → 标记已中标并退出；废标包 → 系统自动开下一轮（仅含废标包）。
    幂等：仅当对应轮次仍「进行中」时才驱动，避免重复确认重复开轮。
    返回提示文案。
    """
    project = db.session.get(Project, result.project_id)
    if not project:
        return ""
    rnd = db.session.execute(
        db.select(ProcurementRound)
        .filter_by(project_id=project.id, round_number=result.round_number or 1)
    ).scalars().first()
    if rnd is None or rnd.status != "进行中":
        return ""  # 无对应轮次或已结束，不重复驱动（兼容旧数据）

    round_pkgs = db.session.execute(
        db.select(RoundPackage).filter_by(round_id=rnd.id)
    ).scalars().all()
    by_no = {}
    for rp in round_pkgs:
        p = db.session.get(Package, rp.package_id)
        if p:
            by_no[p.package_no] = (p, rp)
    ordered = [by_no[k] for k in sorted(by_no)]

    items = []
    try:
        items = json.loads(result.packages_json or "[]")
    except Exception:
        items = []

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    failed = []
    for idx, item in enumerate(items):
        no = item.get("package_no")
        if no in by_no:
            pkg, rp = by_no[no]
        elif idx < len(ordered):
            pkg, rp = ordered[idx]
        else:
            continue
        res = item.get("result", "")
        rp.result = res
        if res == "成交":
            pkg.status = "已中标"
            pkg.won_round = rnd.round_number
            pkg.winner = (item.get("winner") or "").strip()
            pkg.win_amount = float(item.get("amount") or 0)
            rp.winner = pkg.winner
            rp.win_amount = pkg.win_amount
        elif res == "废标":
            failed.append(pkg)

    rnd.status = "已结束"
    if failed:
        next_no = rnd.round_number + 1
        new_round = ProcurementRound(project_id=project.id, round_number=next_no,
                                     status="进行中", created_at=now)
        db.session.add(new_round)
        db.session.flush()
        for pkg in failed:
            db.session.add(RoundPackage(round_id=new_round.id, package_id=pkg.id, result="待定"))
        project.round = next_no
        # 进入下一轮：需重新做采购需求/文件确认（项目镜像位清零）
        project.demand_confirmed = 0
        project.demand_confirmed_by = ""
        project.demand_confirmed_at = ""
        project.doc_confirmed = 0
        project.doc_confirmed_by = ""
        project.doc_confirmed_at = ""
        return f"已确认。包 {('、'.join('包'+str(p.package_no) for p in failed))} 废标，已自动开启第 {next_no} 次采购。"
    else:
        project.status = "已定标"
        return "已确认。本轮全部包成交，项目进入定标/合同阶段。"


@bp.route("", methods=["GET"])
@login_required
def list_results():
    project_id = request.args.get("project_id", type=int)
    q = db.select(ProcurementResult)
    if project_id:
        q = q.where(ProcurementResult.project_id == project_id)
    rows = db.session.execute(q.order_by(ProcurementResult.id.desc())).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("", methods=["POST"])
@login_required
def create_result():
    data = request.get_json(force=True) or {}
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    packages = data.pop("packages", [])

    # 闸门：项目须处于「采购结果」阶段（本轮已确认可开标），且本轮尚未录结果
    pid = data.get("project_id")
    if not pid:
        return jsonify({"ok": False, "error": "请选择项目"}), 400
    from services.project_progress import stage_map
    sm = stage_map([pid]).get(pid, {})
    if sm.get("current_stage") != "result":
        return jsonify({"ok": False, "error": "该项目当前不在采购结果阶段（需先发布公告并确认可开标）"}), 400
    cur_round = sm.get("current_round") or 1
    # 闸门：院内竞选/单一来源，须先在「8.5 项目评审资料上传」上传签字评审结果
    proj = db.session.get(Project, pid)
    if proj and (proj.method or "") in ("院内竞选", "院内单一来源采购"):
        from routes.project_review_api import review_result_uploaded
        if not review_result_uploaded(pid, cur_round):
            return jsonify({"ok": False, "error": "请先在「8.5 项目评审资料上传」上传签字的评审结果，再草拟采购结果确认函"}), 400
    if db.session.execute(
        db.select(ProcurementResult.id).filter_by(project_id=pid, round_number=cur_round)
    ).first():
        return jsonify({"ok": False, "error": "该项目本轮采购结果已存在，请勿重复新建"}), 400

    # 采购结果归属当前轮次：未显式指定时取项目当前轮
    if not data.get("round_number"):
        data["round_number"] = cur_round
    result = ProcurementResult(
        created_by=session.get("display_name", ""),
        created_at=now,
        updated_at=now,
        packages_json=json.dumps(packages, ensure_ascii=False),
        **{k: v for k, v in data.items()
           if hasattr(ProcurementResult, k)
           and k not in ("id", "created_at", "updated_at", "packages_json", "packages")}
    )
    db.session.add(result)
    db.session.commit()
    return jsonify({"ok": True, "data": result.to_dict()})


@bp.route("/<int:rid>", methods=["PUT"])
@login_required
def update_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data = request.get_json(force=True) or {}
    packages = data.pop("packages", None)
    if packages is not None:
        result.packages_json = json.dumps(packages, ensure_ascii=False)
    for k, v in data.items():
        if hasattr(result, k) and k not in ("id", "project_id", "created_by", "created_at", "status", "packages_json", "packages"):
            setattr(result, k, v)
    # 编辑「待确认」内容则退回草稿，需重新提交（避免确认到旧内容）
    if result.status == "待确认":
        result.status = "草稿"
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "data": result.to_dict()})


@bp.route("/<int:rid>", methods=["DELETE"])
@login_required
def delete_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.session.delete(result)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<int:rid>/submit", methods=["POST"])
@login_required
def submit_result(rid):
    """第一步：代理机构（或编制人）提交采购结果 → 待经办人确认。"""
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if result.status == "已确认":
        return jsonify({"ok": False, "error": "已确认，无需重复提交"}), 400
    result.status = "待确认"
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交，等待经办人确认", "data": result.to_dict()})


@bp.route("/<int:rid>/confirm", methods=["POST"])
@login_required
def confirm_result(rid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可确认采购结果"}), 403
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if result.status == "已确认":
        return jsonify({"ok": False, "error": "已确认，请勿重复操作"}), 400
    if result.status != "待确认":
        return jsonify({"ok": False, "error": "请先由代理机构提交后再确认"}), 400
    result.status = "已确认"
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    msg = _apply_result_to_cycle(result)   # 驱动按包循环（成交退出/废标自动开下一轮）
    db.session.commit()
    return jsonify({"ok": True, "message": msg or "已确认"})


@bp.route("/<int:rid>/revoke", methods=["POST"])
@login_required
def revoke_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    # 待确认：代理机构可自行撤回提交；已确认：仅经办人/负责人可撤回
    if result.status == "待确认":
        is_owner_agency = (
            session.get("role") == "agency"
            and _project_agency(result.project_id) == session.get("agency_code", "")
        )
        if not (_can_confirm() or is_owner_agency):
            return jsonify({"ok": False, "error": "无权撤回"}), 403
    else:
        if not _can_confirm():
            return jsonify({"ok": False, "error": "仅项目经办人或负责人可撤回采购结果"}), 403
    # 若该结果已触发后续轮次（开了下一轮），不允许撤回，以免轮次/包状态错乱
    later = db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=result.project_id)
        .where(ProcurementRound.round_number > (result.round_number or 1))
    ).first()
    if later:
        return jsonify({"ok": False, "error": "该轮结果已触发下一轮采购，无法撤回"}), 400
    result.status = "草稿"
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回为草稿"})


@bp.route("/<int:rid>/word", methods=["GET"])
@login_required
def generate_word(rid):
    """生成采购结果确认函 Word 文档"""
    from services.procurement_result_word import generate
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    project = db.session.get(Project, result.project_id)
    try:
        buf, filename = generate(result, project)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500


# ─────────────────────────────────────────────────────────────────
# 单价附件：招单价项目「单价详见附件」上传/下载/删除
# 复用 ProcurementDocAttachment 表（kind='result'），按结果所属项目+轮次归档。
# ─────────────────────────────────────────────────────────────────
def _price_query(result):
    return (
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id == result.project_id)
        .where(ProcurementDocAttachment.kind == "result")
        .where(ProcurementDocAttachment.round_number == (result.round_number or 1))
        .order_by(ProcurementDocAttachment.id)
    )


@bp.route("/<int:rid>/price-attachments", methods=["GET"])
@login_required
def list_price_attachments(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    rows = db.session.execute(_price_query(result)).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:rid>/price-attachments", methods=["POST"])
@login_required
def upload_price_attachment(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if result.status == "已确认":
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤回"}), 400

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False, "error": f"不支持的文件格式：{ext}，支持 PDF/Word/Excel/图片/压缩包"}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(_price_attach_dir(result.project_id), saved_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    sha256 = _sha256_of(save_path)

    att = ProcurementDocAttachment(
        project_id=result.project_id,
        kind="result",
        round_number=result.round_number or 1,
        original_name=f.filename,
        saved_name=saved_name,
        file_size=file_size,
        sha256=sha256,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "上传成功", "data": att.to_dict()}), 201


def _get_price_att(rid, aid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return None, None
    att = db.session.get(ProcurementDocAttachment, aid)
    if (not att or att.project_id != result.project_id
            or att.kind != "result"
            or att.round_number != (result.round_number or 1)):
        return result, None
    return result, att


@bp.route("/<int:rid>/price-attachments/<int:aid>", methods=["GET"])
@login_required
def download_price_attachment(rid, aid):
    result, att = _get_price_att(rid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_price_attach_dir(result.project_id), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


@bp.route("/<int:rid>/price-attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview_price_attachment(rid, aid):
    result, att = _get_price_att(rid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_price_attach_dir(result.project_id), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=False, download_name=att.original_name)


@bp.route("/<int:rid>/price-attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete_price_attachment(rid, aid):
    result, att = _get_price_att(rid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if result.status == "已确认":
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤回"}), 400
    try:
        path = os.path.join(_price_attach_dir(result.project_id), att.saved_name)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ─────────────────────────────────────────────────────────────────
# 中标通知书：经办人确认采购结果后，代理机构上传中标通知书。
# 未上传则合同管理无法立项（见 contract_api.create_contract 闸门）。
# 复用 ProcurementDocAttachment 表（kind='award_notice'），按项目+轮次归档。
# ─────────────────────────────────────────────────────────────────
def _award_query(result):
    return (
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id == result.project_id)
        .where(ProcurementDocAttachment.kind == "award_notice")
        .where(ProcurementDocAttachment.round_number == (result.round_number or 1))
        .order_by(ProcurementDocAttachment.id)
    )


def _can_upload_award(result) -> bool:
    """中标通知书：本项目代理机构 或 采购人方（经办人/助理/负责人）可上传/删除。"""
    if _can_confirm():
        return True
    return (
        session.get("role") == "agency"
        and _project_agency(result.project_id) == session.get("agency_code", "")
    )


def _result_has_winner(result) -> bool:
    """采购结果是否存在成交包。全部废标则无中标通知书。"""
    try:
        items = json.loads(result.packages_json or "[]")
    except Exception:
        items = []
    return any((it.get("result") == "成交") for it in items)


@bp.route("/<int:rid>/award-notice", methods=["GET"])
@login_required
def list_award_notice(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    rows = db.session.execute(_award_query(result)).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:rid>/award-notice", methods=["POST"])
@login_required
def upload_award_notice(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if result.status != "已确认":
        return jsonify({"ok": False, "error": "采购结果经办人确认后方可上传中标通知书"}), 400
    if not _result_has_winner(result):
        return jsonify({"ok": False, "error": "本次采购结果全部废标，无成交包，无需上传中标通知书"}), 400
    if not _can_upload_award(result):
        return jsonify({"ok": False, "error": "仅本项目代理机构或采购人方可上传中标通知书"}), 403

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False, "error": f"不支持的文件格式：{ext}，支持 PDF/Word/Excel/图片/压缩包"}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(_price_attach_dir(result.project_id), saved_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    sha256 = _sha256_of(save_path)

    att = ProcurementDocAttachment(
        project_id=result.project_id,
        kind="award_notice",
        round_number=result.round_number or 1,
        original_name=f.filename,
        saved_name=saved_name,
        file_size=file_size,
        sha256=sha256,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=datetime.now().isoformat(timespec="seconds"),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "上传成功", "data": att.to_dict()}), 201


def _get_award_att(rid, aid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return None, None
    att = db.session.get(ProcurementDocAttachment, aid)
    if (not att or att.project_id != result.project_id
            or att.kind != "award_notice"
            or att.round_number != (result.round_number or 1)):
        return result, None
    return result, att


@bp.route("/<int:rid>/award-notice/<int:aid>", methods=["GET"])
@login_required
def download_award_notice(rid, aid):
    result, att = _get_award_att(rid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_price_attach_dir(result.project_id), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


@bp.route("/<int:rid>/award-notice/<int:aid>/preview", methods=["GET"])
@login_required
def preview_award_notice(rid, aid):
    result, att = _get_award_att(rid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_price_attach_dir(result.project_id), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=False, download_name=att.original_name)


@bp.route("/<int:rid>/award-notice/<int:aid>", methods=["DELETE"])
@login_required
def delete_award_notice(rid, aid):
    result, att = _get_award_att(rid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if not _can_upload_award(result):
        return jsonify({"ok": False, "error": "无权删除"}), 403
    try:
        path = os.path.join(_price_attach_dir(result.project_id), att.saved_name)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})
