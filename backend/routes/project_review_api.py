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
from routes.utils import login_required
from services.permission import is_admin_user
from services.project_progress import stage_map

bp = Blueprint("project_review", __name__, url_prefix="/api/project-review")

UPLOAD_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "uploads", "project_review"))
KIND = "review_result"
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
        if st.get("current_stage") != "result":
            continue
        if role == "agency" and p.agency_code != ag:
            continue
        if role == "officer" and p.officer != me:
            continue
        rnd = st.get("current_round") or 1
        d = p.to_dict()
        d["current_round"] = rnd
        d["attachments"] = [a.to_dict() for a in _atts(p.id, rnd)]
        out.append(d)
    return jsonify({"ok": True, "data": out})


def _proj_round(pid):
    return (stage_map([pid]).get(pid, {}) or {}).get("current_round") or 1


@bp.route("/<int:pid>/attachments", methods=["POST"])
@login_required
def upload(pid):
    if not _can_upload():
        return jsonify({"ok": False, "error": "无权限"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
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
    return att


@bp.route("/<int:pid>/attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview(pid, aid):
    att = _get_att(pid, aid)
    if not att:
        return jsonify({"ok": False, "error": "不存在"}), 404
    return send_file(os.path.join(_dir(pid), att.saved_name),
                     as_attachment=False, download_name=att.original_name)


@bp.route("/<int:pid>/attachments/<int:aid>/download", methods=["GET"])
@login_required
def download(pid, aid):
    att = _get_att(pid, aid)
    if not att:
        return jsonify({"ok": False, "error": "不存在"}), 404
    return send_file(os.path.join(_dir(pid), att.saved_name),
                     as_attachment=True, download_name=att.original_name)


@bp.route("/<int:pid>/attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete(pid, aid):
    if not _can_upload():
        return jsonify({"ok": False, "error": "无权限"}), 403
    att = _get_att(pid, aid)
    if not att:
        return jsonify({"ok": False, "error": "不存在"}), 404
    try:
        os.remove(os.path.join(_dir(pid), att.saved_name))
    except OSError:
        pass
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True})
