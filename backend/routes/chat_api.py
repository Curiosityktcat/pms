"""聊天（站内即时通讯）  —  /api/chat

一对一聊天，支持文本 / 图片 / 文件（≤20MB），已读未读。对所有登录用户开放（含代理）。
"""
import datetime
import os
import time
import uuid

from flask import Blueprint, request, session, jsonify, send_file

from models import db
from models.chat_message import ChatMessage
from models.user import User
from routes.utils import login_required

bp = Blueprint("chat", __name__, url_prefix="/api/chat")

HERE = os.path.dirname(os.path.abspath(__file__))
PMS_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CHAT_DIR = os.path.join(PMS_ROOT, "聊天附件")

MAX_SIZE = 20 * 1024 * 1024  # 20MB
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
FILE_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".txt", ".csv", ".zip", ".rar", ".7z"}
ALLOWED_EXT = IMAGE_EXT | FILE_EXT


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _me():
    return session.get("user", ""), session.get("display_name", "")


# ─────────────────────────────────────────────────────────────────
# 角标 + 联系人
# ─────────────────────────────────────────────────────────────────

@bp.route("/summary", methods=["GET"])
@login_required
def summary():
    me, _ = _me()
    unread = db.session.execute(
        db.select(db.func.count(ChatMessage.id)).where(
            ChatMessage.recipient == me, ChatMessage.is_read == 0)
    ).scalar() or 0
    return jsonify({"ok": True, "data": {"unread": int(unread)}})


@bp.route("/contacts", methods=["GET"])
@login_required
def contacts():
    """联系人列表：所有启用用户（除自己），带与我的最近一条消息、未读数。
    有聊天记录的按最近时间倒序在前，其余按用户顺序排后。"""
    me, _ = _me()
    users = db.session.execute(
        db.select(User).where(User.active == 1).order_by(User.id)
    ).scalars().all()

    # 一次性载入与我相关的全部消息，内存里按对端归并（规模小）
    msgs = db.session.execute(
        db.select(ChatMessage).where(
            db.or_(ChatMessage.sender == me, ChatMessage.recipient == me)
        ).order_by(ChatMessage.id.asc())
    ).scalars().all()

    last_by_peer = {}
    unread_by_peer = {}
    for m in msgs:
        peer = m.recipient if m.sender == me else m.sender
        last_by_peer[peer] = m  # 升序遍历，最终留最新
        if m.recipient == me and not m.is_read:
            unread_by_peer[peer] = unread_by_peer.get(peer, 0) + 1

    def _preview(m):
        if not m:
            return ""
        if m.msg_type == "image":
            return "[图片]"
        if m.msg_type == "file":
            return f"[文件] {m.file_name}"
        return (m.text or "")[:30]

    rows = []
    for u in users:
        if u.username == me:
            continue
        m = last_by_peer.get(u.username)
        rows.append({
            "username": u.username,
            "display_name": u.display_name or u.username,
            "role": u.role,
            "unread": unread_by_peer.get(u.username, 0),
            "last_text": _preview(m),
            "last_time": m.created_at if m else "",
            "last_id": m.id if m else 0,
        })
    # 有消息的按时间倒序在前，无消息的保持用户顺序在后
    rows.sort(key=lambda r: (r["last_time"] or "", r["last_id"]), reverse=True)
    rows.sort(key=lambda r: 0 if r["last_time"] else 1)
    return jsonify({"ok": True, "data": rows})


# ─────────────────────────────────────────────────────────────────
# 会话消息
# ─────────────────────────────────────────────────────────────────

def _peer_user(peer):
    return db.session.execute(
        db.select(User).filter_by(username=peer)).scalar_one_or_none()


@bp.route("/messages", methods=["GET"])
@login_required
def messages():
    """拉取我与 peer 的会话（升序），并把 peer→我 的未读标记为已读。"""
    me, _ = _me()
    peer = request.args.get("peer", "")
    pu = _peer_user(peer)
    if not pu:
        return jsonify({"ok": False, "error": "联系人不存在"}), 404

    rows = db.session.execute(
        db.select(ChatMessage).where(
            db.or_(
                db.and_(ChatMessage.sender == me, ChatMessage.recipient == peer),
                db.and_(ChatMessage.sender == peer, ChatMessage.recipient == me),
            )
        ).order_by(ChatMessage.id.asc())
    ).scalars().all()

    now = _now()
    changed = False
    for m in rows:
        if m.recipient == me and not m.is_read:
            m.is_read = 1
            m.read_at = now
            changed = True
    if changed:
        db.session.commit()

    return jsonify({"ok": True, "data": [m.to_dict() for m in rows],
                    "peer": {"username": pu.username,
                             "display_name": pu.display_name or pu.username}})


@bp.route("/read", methods=["POST"])
@login_required
def mark_read():
    me, _ = _me()
    data = request.get_json(force=True) or {}
    peer = data.get("peer", "")
    now = _now()
    rows = db.session.execute(
        db.select(ChatMessage).where(
            ChatMessage.sender == peer, ChatMessage.recipient == me,
            ChatMessage.is_read == 0)
    ).scalars().all()
    for m in rows:
        m.is_read = 1
        m.read_at = now
    db.session.commit()
    return jsonify({"ok": True, "read": len(rows)})


def _send(recipient, msg_type, text="", file_path="", file_name="", file_size=0):
    me, my_name = _me()
    pu = _peer_user(recipient)
    if not pu:
        return None, "收件人不存在"
    if recipient == me:
        return None, "不能给自己发消息"
    m = ChatMessage(
        sender=me, sender_name=my_name,
        recipient=recipient, recipient_name=pu.display_name or pu.username,
        msg_type=msg_type, text=text,
        file_path=file_path, file_name=file_name, file_size=file_size,
        is_read=0, created_at=_now(),
    )
    db.session.add(m)
    db.session.commit()
    return m, None


@bp.route("/messages", methods=["POST"])
@login_required
def send_text():
    data = request.get_json(force=True) or {}
    recipient = data.get("recipient", "")
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "error": "消息不能为空"}), 400
    m, err = _send(recipient, "text", text=text)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "data": m.to_dict()}), 201


@bp.route("/messages/file", methods=["POST"])
@login_required
def send_file_msg():
    recipient = request.form.get("recipient", "")
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    f = request.files["file"]
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"不支持的文件格式 {ext}"}), 400

    # 体积校验（20MB）
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size > MAX_SIZE:
        return jsonify({"ok": False, "error": "文件超过 20MB 限制"}), 400
    if size == 0:
        return jsonify({"ok": False, "error": "空文件"}), 400

    os.makedirs(CHAT_DIR, exist_ok=True)
    saved = f"{uuid.uuid4().hex}{ext}"
    f.save(os.path.join(CHAT_DIR, saved))

    msg_type = "image" if ext in IMAGE_EXT else "file"
    m, err = _send(recipient, msg_type,
                   text=request.form.get("text", ""),
                   file_path=f"聊天附件/{saved}",
                   file_name=f.filename, file_size=size)
    if err:
        try:
            os.remove(os.path.join(CHAT_DIR, saved))
        except OSError:
            pass
        return jsonify({"ok": False, "error": err}), 400
    return jsonify({"ok": True, "data": m.to_dict()}), 201


@bp.route("/files/<int:mid>", methods=["GET"])
@login_required
def get_file(mid):
    """预览/下载聊天文件，仅收发双方可访问。download=1 强制下载。"""
    me, _ = _me()
    m = db.session.get(ChatMessage, mid)
    if not m or me not in (m.sender, m.recipient):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    if not m.file_path:
        return jsonify({"ok": False, "error": "该消息无文件"}), 404
    full = os.path.join(PMS_ROOT, m.file_path)
    if not os.path.exists(full):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    as_attach = request.args.get("download") == "1" or m.msg_type == "file"
    return send_file(full, as_attachment=as_attach, download_name=m.file_name)
