"""8.5 项目评审资料上传。

用于 院内竞选 / 院内单一来源采购 项目：代理机构完成「可开标」判定、线下开标评审后，
把**签字的评审结果**上传到这里（kind='review_result'，按项目+轮次归档），
之后才能在「9. 采购结果确认」草拟采购结果确认函（见 procurement_result_api 的门禁）。
"""
import os
import uuid
import datetime

from flask import Blueprint, request, jsonify, session, send_file

from models import db
from models.project import Project
from models.procurement_doc_attachment import ProcurementDocAttachment
from models.procurement_round import ProcurementRound
from routes.utils import login_required, can_view_project
from services import approval_log as alog
from services.permission import is_admin_user
from services.project_progress import stage_map

bp = Blueprint("project_review", __name__, url_prefix="/api/project-review")

UPLOAD_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "uploads", "project_review"))
KIND = "review_result"

from services import storage as _storage        # noqa: E402  对象存储抽象层


def _rel(pid, saved_name):
    """附件的存储键：本地和 OSS 用同一个公式，库里存的 saved_name 不变。"""
    return f"uploads/project_review/{pid}/{saved_name}"
METHODS = ("院内竞选", "院内单一来源采购")
ALLOWED = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".gif", ".zip", ".rar"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _dir(pid):
    d = os.path.join(UPLOAD_ROOT, str(pid))
    os.makedirs(d, exist_ok=True)
    return d


def _can_upload():
    return (session.get("role") in ("agency", "officer", "assistant", "pd_assistant", "leader")
            or is_admin_user(session.get("user", "")))


def _atts(pid, rnd):
    return db.session.execute(
        db.select(ProcurementDocAttachment)
        .filter_by(project_id=pid, kind=KIND, round_number=rnd or 1)
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()


def _all_atts(pid):
    """该项目全部轮次的评审结果附件（历史也可见）。"""
    return db.session.execute(
        db.select(ProcurementDocAttachment)
        .filter_by(project_id=pid, kind=KIND)
        .order_by(ProcurementDocAttachment.round_number, ProcurementDocAttachment.id)
    ).scalars().all()


def review_result_uploaded(pid, rnd):
    """该项目该轮是否已上传签字评审结果（供采购结果确认门禁调用）。"""
    return db.session.execute(
        db.select(ProcurementDocAttachment.id)
        .filter_by(project_id=pid, kind=KIND, round_number=rnd or 1)
    ).first() is not None


# ── 待上传评审结果的项目（院内竞选/单一来源，处于采购结果阶段）──────
@bp.route("/projects", methods=["GET"])
@login_required
def list_projects():
    rows = db.session.execute(db.select(Project).where(
        Project.method.in_(METHODS),
        db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
    )).scalars().all()
    pids = [p.id for p in rows]
    sm = stage_map(pids) if pids else {}
    role = session.get("role")
    ag = session.get("agency_code", "")
    me = session.get("display_name", "")
    out = []
    for p in rows:
        st = sm.get(p.id, {})
        stage = st.get("current_stage")
        all_atts = _all_atts(p.id)
        # 处于采购结果阶段（待/可上传），或已上传过评审结果（历史查看）——都保留可见
        if stage != "result" and not all_atts:
            continue
        if role == "agency" and p.agency_code != ag:
            continue
        if role == "officer" and p.officer != me:
            continue
        rnd = st.get("current_round") or 1
        d = p.to_dict()
        d["current_round"] = rnd
        # 展示全部轮次已上传的评审结果（推进到后续阶段后仍能查看历史资料）
        d["attachments"] = [a.to_dict() for a in all_atts]
        d["past_result"] = stage != "result"
        # 本轮评审资料的审核状态（供前端显示确认/驳回按钮与驳回原因）
        row = db.session.execute(
            db.select(ProcurementRound).filter_by(project_id=p.id, round_number=rnd)
        ).scalars().first()
        d["review_status"] = (row.review_status if row else "") or ""
        d["review_reject_reason"] = (row.review_reject_reason if row else "") or ""
        d["review_reject_count"] = int((row.review_reject_count if row else 0) or 0)
        d["review_confirmed_by"] = (row.review_confirmed_by if row else "") or ""
        d["review_confirmed_at"] = (row.review_confirmed_at if row else "") or ""
        out.append(d)
    return jsonify({"ok": True, "data": out})


def _proj_round(pid):
    return (stage_map([pid]).get(pid, {}) or {}).get("current_round") or 1


# ══════════════════════════════════════════════════════════════════
# 评审资料审核：代理提交 → 经办人确认 / 驳回（可反复，全程留痕）
# ══════════════════════════════════════════════════════════════════

def _round_row(pid, rnd=None):
    """取本项目当前轮次记录；没有则返回 None（旧数据兼容）。"""
    rnd = rnd or _proj_round(pid)
    return db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=pid, round_number=rnd)
    ).scalars().first()


def _can_confirm_review():
    return (session.get("role") in ("officer", "assistant", "leader")
            or is_admin_user(session.get("user", "")))


@bp.route("/<int:pid>/submit", methods=["POST"])
@login_required
def submit_review(pid):
    """代理机构把已上传的评审资料提交给经办人审核。"""
    project = db.session.get(Project, pid)
    if not project or not can_view_project(project):
        return jsonify({"ok": False, "error": "项目不存在或无权访问"}), 404
    if not _can_upload():
        return jsonify({"ok": False, "error": "权限不足"}), 403
    rnd = _proj_round(pid)
    if not _atts(pid, rnd):
        return jsonify({"ok": False, "error": "本轮尚未上传评审资料，无法提交"}), 400
    row = _round_row(pid, rnd)
    if row is None:
        return jsonify({"ok": False, "error": "本项目暂无采购轮次记录"}), 400
    was_rejected = row.review_status == "已驳回"
    row.review_status = "待确认"
    alog.log(pid, "review", "resubmit" if was_rejected else "submit", round_number=rnd)
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交，等待经办人确认", "data": row.to_dict()})


@bp.route("/<int:pid>/confirm", methods=["POST"])
@login_required
def confirm_review(pid):
    project = db.session.get(Project, pid)
    if not project or not can_view_project(project):
        return jsonify({"ok": False, "error": "项目不存在或无权访问"}), 404
    if not _can_confirm_review():
        return jsonify({"ok": False, "error": "仅经办人或负责人可确认评审资料"}), 403
    rnd = _proj_round(pid)
    row = _round_row(pid, rnd)
    if row is None:
        return jsonify({"ok": False, "error": "本项目暂无采购轮次记录"}), 400
    row.review_status = "已确认"
    row.review_confirmed_by = session.get("display_name", "")
    row.review_confirmed_at = _now()
    row.review_reject_reason = ""
    alog.log(pid, "review", "confirm", round_number=rnd)
    db.session.commit()
    return jsonify({"ok": True, "message": "评审资料已确认", "data": row.to_dict()})


@bp.route("/<int:pid>/reject", methods=["POST"])
@login_required
def reject_review(pid):
    """驳回评审资料：写明原因，代理机构补件或重传后再次提交。"""
    project = db.session.get(Project, pid)
    if not project or not can_view_project(project):
        return jsonify({"ok": False, "error": "项目不存在或无权访问"}), 404
    if not _can_confirm_review():
        return jsonify({"ok": False, "error": "仅经办人或负责人可驳回评审资料"}), 403
    reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "请填写驳回原因"}), 400
    rnd = _proj_round(pid)
    row = _round_row(pid, rnd)
    if row is None:
        return jsonify({"ok": False, "error": "本项目暂无采购轮次记录"}), 400
    row.review_status = "已驳回"
    row.review_reject_reason = reason
    row.review_reject_count = int(row.review_reject_count or 0) + 1
    row.review_rejected_by = session.get("display_name", "")
    row.review_rejected_at = _now()
    row.review_confirmed_by = ""
    row.review_confirmed_at = ""
    alog.log(pid, "review", "reject", round_number=rnd, reason=reason)
    db.session.commit()
    return jsonify({"ok": True,
                    "message": f"已驳回（第{row.review_reject_count}次），代理机构可补件后重新提交",
                    "data": row.to_dict()})


@bp.route("/<int:pid>/attachments/register", methods=["POST"])
@login_required
def register_direct(pid):
    """直传回调：浏览器已把文件 PUT 到 OSS，这里只登记元数据。
    **不信前端报的大小**，回头找对象存储核实，免得有人报个假尺寸。"""
    if not _can_upload():
        return jsonify({"ok": False, "error": "无权限"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_view_project(p):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    d = request.get_json(force=True, silent=True) or {}
    rel = (d.get("rel_path") or "").replace("\\", "/").lstrip("/")
    filename = (d.get("filename") or "").strip()
    prefix = f"uploads/project_review/{pid}/"
    # 路径必须落在本项目自己的目录下，否则就是想往别处写
    if not rel.startswith(prefix) or ".." in rel:
        return jsonify({"ok": False, "error": "路径不合法"}), 400
    _, ext = os.path.splitext(filename.lower())
    if ext not in ALLOWED:
        return jsonify({"ok": False, "error": f"不支持的格式：{ext}"}), 400
    if not _storage.exists(rel):
        return jsonify({"ok": False, "error": "对象存储上没找到该文件，可能上传中断"}), 400
    saved = rel[len(prefix):]
    size = 0
    try:
        where, val = _storage.resolve(rel)
        if where == "local":
            size = os.path.getsize(val)
        else:
            size = int(_storage._b().head_object(_storage._key(rel)).content_length)
    except Exception:
        size = int(d.get("size") or 0)
    att = ProcurementDocAttachment(
        project_id=pid, kind=KIND, round_number=_proj_round(pid),
        original_name=filename, saved_name=saved,
        file_size=size, uploaded_by=session.get("display_name", ""),
        uploaded_at=_now())
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "data": att.to_dict()}), 201


@bp.route("/<int:pid>/attachments", methods=["POST"])
@login_required
def upload(pid):
    if not _can_upload():
        return jsonify({"ok": False, "error": "无权限"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_view_project(p):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED:
        return jsonify({"ok": False, "error": f"不支持的格式：{ext}"}), 400
    saved = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(_dir(pid), saved)
    f.save(path)
    att = ProcurementDocAttachment(
        project_id=pid, kind=KIND, round_number=_proj_round(pid),
        original_name=f.filename, saved_name=saved,
        file_size=os.path.getsize(path), uploaded_by=session.get("display_name", ""),
        uploaded_at=_now())
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "data": att.to_dict()}), 201


def _get_att(pid, aid):
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid or att.kind != KIND:
        return None
    # 归属校验：officer 本人经办 / agency 本机构 / 助理·负责人·管理员
    if not can_view_project(db.session.get(Project, pid)):
        return None
    return att


@bp.route("/<int:pid>/attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview(pid, aid):
    att = _get_att(pid, aid)
    if not att:
        return jsonify({"ok": False, "error": "不存在"}), 404
    where, val = _storage.resolve(_rel(pid, att.saved_name))
    if where == "oss":
        from flask import redirect
        return redirect(_storage.signed_url(_rel(pid, att.saved_name),
                                            filename=att.original_name, inline=True), code=302)
    from services.office_convert import send_preview
    return send_preview(val or os.path.join(_dir(pid), att.saved_name), att.original_name)


@bp.route("/<int:pid>/attachments/<int:aid>/download", methods=["GET"])
@login_required
def download(pid, aid):
    att = _get_att(pid, aid)
    if not att:
        return jsonify({"ok": False, "error": "不存在"}), 404
    where, val = _storage.resolve(_rel(pid, att.saved_name))
    if where == "oss":
        from flask import redirect
        return redirect(_storage.signed_url(_rel(pid, att.saved_name),
                                            filename=att.original_name), code=302)
    if not val:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(val, as_attachment=True, download_name=att.original_name)


@bp.route("/<int:pid>/attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete(pid, aid):
    if not _can_upload():
        return jsonify({"ok": False, "error": "无权限"}), 403
    att = _get_att(pid, aid)
    if not att:
        return jsonify({"ok": False, "error": "不存在"}), 404
    _storage.delete(_rel(pid, att.saved_name))   # 本地与 OSS 都删，避免留幽灵文件
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True})
