"""采购部公告和相关文件（分流页）。

经办人（内部账号）上传 → 审核人（陈梦霞，或系统管理员代审）通过后发布，全员可见。
代理机构账号只能看已发布内容。
"""
import datetime
import os
import uuid

from flask import Blueprint, request, session, jsonify, send_file

from models import db
from models.dept_announcement import DeptAnnouncement
from routes.utils import login_required
from services.permission import is_admin_user
from services import upload_relay

bp = Blueprint("dept_announcement", __name__, url_prefix="/api/dept-announcements")

PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
UPLOAD_DIR = os.path.join(PMS_ROOT, "uploads", "dept_announcements")
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
               ".png", ".jpg", ".jpeg", ".zip", ".rar", ".txt", ".md"}

REVIEWER = "陈梦霞"   # 审核人（users.display_name）


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _is_reviewer():
    return (session.get("display_name") == REVIEWER
            or is_admin_user(session.get("user", "")))


# 采购部内部角色。这个公告栏是**采购部往下发**的，不是大家互相发。
CGB_ROLES = ("officer", "assistant", "pd_assistant", "leader")


def _can_upload():
    """谁能往采购部公告栏发东西。

    2026-08-19 收紧：原来是「只要不是代理机构就能传」，那时候系统里只有采购部
    的人。现在 59 个科室账号进来了，照旧的话每个科室都能往全院公告栏发文件。
    黄新博的原话是「所有进入系统的人都**可以看得到**」——看是所有人，发还是采购部。
    """
    from services.permission import is_admin_user
    return (session.get("role", "") in CGB_ROLES
            or is_admin_user(session.get("user", "")))


@bp.route("", methods=["GET"])
@login_required
def list_announcements():
    """已发布=全员可见；待审核/已驳回=上传人自己和审核人可见。"""
    rows = db.session.execute(
        db.select(DeptAnnouncement).order_by(DeptAnnouncement.id.desc())
    ).scalars().all()
    me = session.get("display_name", "")
    reviewer = _is_reviewer()
    out = []
    for r in rows:
        if r.status != "已发布" and not reviewer and r.uploaded_by != me:
            continue
        out.append(r.to_dict())
    return jsonify({"ok": True, "data": out, "is_reviewer": reviewer,
                    "can_upload": _can_upload()})


@bp.route("", methods=["POST"])
@login_required
def create_announcement():
    if not _can_upload():
        return jsonify({"ok": False, "error": "代理机构账号不能上传采购部公告"}), 403
    title = (request.form.get("title") or "").strip()
    note = (request.form.get("note") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "请填写公告标题"}), 400

    filename, saved_name, size = "", "", 0
    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if f and f.filename:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext not in ALLOWED_EXT:
            return jsonify({"ok": False, "error": f"不支持的文件格式：{ext}"}), 400
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        saved_name = f"{uuid.uuid4().hex}{ext}"
        f.save(os.path.join(UPLOAD_DIR, saved_name))
        size = os.path.getsize(os.path.join(UPLOAD_DIR, saved_name))
        filename = f.filename

    row = DeptAnnouncement(
        title=title, note=note,
        filename=filename, saved_name=saved_name, file_size=size,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=_now(),
        status="待审核",
    )
    # 审核人自己上传的直接发布（自己审自己没有意义）
    if _is_reviewer():
        row.status = "已发布"
        row.reviewed_by = session.get("display_name", "")
        row.reviewed_at = _now()
    db.session.add(row)
    db.session.commit()
    msg = "已发布" if row.status == "已发布" else f"已提交，等待{REVIEWER}审核后发布"
    return jsonify({"ok": True, "message": msg, "data": row.to_dict()}), 201


@bp.route("/<int:aid>/review", methods=["POST"])
@login_required
def review_announcement(aid):
    if not _is_reviewer():
        return jsonify({"ok": False, "error": f"仅{REVIEWER}可审核"}), 403
    row = db.session.get(DeptAnnouncement, aid)
    if not row:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    if row.status != "待审核":
        return jsonify({"ok": False, "error": "该条不是待审核状态"}), 400
    data = request.get_json(force=True) or {}
    action = data.get("action")
    if action == "approve":
        row.status = "已发布"
    elif action == "reject":
        row.status = "已驳回"
        row.reject_reason = (data.get("reason") or "").strip()
    else:
        return jsonify({"ok": False, "error": "未知操作"}), 400
    row.reviewed_by = session.get("display_name", "")
    row.reviewed_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": f"已{('发布' if action == 'approve' else '驳回')}",
                    "data": row.to_dict()})


@bp.route("/<int:aid>", methods=["DELETE"])
@login_required
def delete_announcement(aid):
    row = db.session.get(DeptAnnouncement, aid)
    if not row:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    me = session.get("display_name", "")
    # 审核人可删任意；上传人只能删自己的未发布条目
    if not _is_reviewer() and not (row.uploaded_by == me and row.status != "已发布"):
        return jsonify({"ok": False, "error": "无权删除"}), 403
    if row.saved_name:
        p = os.path.join(UPLOAD_DIR, row.saved_name)
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<int:aid>/download", methods=["GET"])
@login_required
def download_announcement(aid):
    row = db.session.get(DeptAnnouncement, aid)
    if not row or not row.saved_name:
        return jsonify({"ok": False, "error": "无附件"}), 404
    me = session.get("display_name", "")
    if row.status != "已发布" and not _is_reviewer() and row.uploaded_by != me:
        return jsonify({"ok": False, "error": "未发布"}), 403
    p = os.path.join(UPLOAD_DIR, row.saved_name)
    if not os.path.exists(p):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    return send_file(p, as_attachment=True, download_name=row.filename or "附件")
