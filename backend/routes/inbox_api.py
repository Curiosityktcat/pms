"""待办  —  /api/inbox

对所有登录用户开放（含代理机构）。待办只对自己相关者可见（owner 或 created_by）。
系统事件按项目阶段自动派单给经办人/代理（source=system），事项完成自动消除，
不可手动操作；见 services/system_todos.py。站内信已改为独立的「聊天」模块（chat_api）。
"""
import datetime

from flask import Blueprint, request, session, jsonify

from models import db
from models.todo import Todo
from models.user import User
from routes.utils import login_required
from services.system_todos import maybe_reconcile

bp = Blueprint("inbox", __name__, url_prefix="/api/inbox")

PRIORITIES = ("普通", "重要", "紧急")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _me():
    return session.get("user", ""), session.get("display_name", "")


# ─────────────────────────────────────────────────────────────────
# 角标汇总 + 用户列表
# ─────────────────────────────────────────────────────────────────

@bp.route("/summary", methods=["GET"])
@login_required
def summary():
    """顶栏铃铛角标：待办（未完成）数。先按需对账系统待办。"""
    maybe_reconcile()
    me, _ = _me()
    pending = db.session.execute(
        db.select(db.func.count(Todo.id)).where(
            Todo.owner == me, Todo.status == "待办"
        )
    ).scalar() or 0
    return jsonify({"ok": True, "data": {
        "pending_todos": int(pending),
        "total": int(pending),
    }})


@bp.route("/users", methods=["GET"])
@login_required
def list_users():
    """可选收件人 / 指派对象：启用的用户（排除自己），代理机构也在列。"""
    me, _ = _me()
    rows = db.session.execute(
        db.select(User).where(User.active == 1).order_by(User.id)
    ).scalars().all()
    data = [{
        "username": u.username,
        "display_name": u.display_name or u.username,
        "role": u.role,
    } for u in rows if u.username != me]
    return jsonify({"ok": True, "data": data})


# ─────────────────────────────────────────────────────────────────
# 待办
# ─────────────────────────────────────────────────────────────────

@bp.route("/todos", methods=["GET"])
@login_required
def list_todos():
    """status=待办|已完成|all（默认 all）；scope=mine（指派给我，默认）|created（我创建的）|both"""
    maybe_reconcile()
    me, _ = _me()
    status = request.args.get("status", "all")
    scope = request.args.get("scope", "both")
    conds = []
    if scope == "mine":
        conds.append(Todo.owner == me)
    elif scope == "created":
        conds.append(Todo.created_by == me)
    else:
        conds.append(db.or_(Todo.owner == me, Todo.created_by == me))
    if status in ("待办", "已完成"):
        conds.append(Todo.status == status)
    rows = db.session.execute(
        db.select(Todo).where(*conds).order_by(Todo.status, Todo.id.desc())
    ).scalars().all()
    return jsonify({"ok": True, "data": [t.to_dict() for t in rows]})


@bp.route("/todos", methods=["POST"])
@login_required
def create_todo():
    me, my_name = _me()
    data = request.get_json(force=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"ok": False, "error": "请填写待办标题"}), 400

    owner = data.get("owner") or me
    owner_name = data.get("owner_name") or ""
    if owner == me:
        owner_name = my_name
    elif not owner_name:
        u = db.session.execute(
            db.select(User).filter_by(username=owner)).scalar_one_or_none()
        owner_name = (u.display_name or u.username) if u else owner

    priority = data.get("priority", "普通")
    if priority not in PRIORITIES:
        priority = "普通"

    todo = Todo(
        owner=owner, owner_name=owner_name,
        title=title, content=data.get("content", ""),
        status="待办", priority=priority,
        due_date=data.get("due_date", ""),
        related_project_id=data.get("related_project_id"),
        related_project_name=data.get("related_project_name", ""),
        created_by=me, created_by_name=my_name,
        created_at=_now(), source="manual",
    )
    db.session.add(todo)
    db.session.commit()
    return jsonify({"ok": True, "data": todo.to_dict()}), 201


def _get_my_todo(tid):
    me, _ = _me()
    t = db.session.get(Todo, tid)
    if not t or me not in (t.owner, t.created_by):
        return None
    return t


_SYSTEM_GUARD = (
    "系统待办由项目阶段自动生成，完成对应事项后会自动消除，不能手动操作"
)


@bp.route("/todos/<int:tid>", methods=["PUT"])
@login_required
def update_todo(tid):
    t = _get_my_todo(tid)
    if not t:
        return jsonify({"ok": False, "error": "待办不存在"}), 404
    if t.source == "system":
        return jsonify({"ok": False, "error": _SYSTEM_GUARD}), 400
    data = request.get_json(force=True) or {}
    for f in ("title", "content", "due_date", "related_project_name"):
        if f in data:
            setattr(t, f, data[f])
    if "priority" in data and data["priority"] in PRIORITIES:
        t.priority = data["priority"]
    if "related_project_id" in data:
        t.related_project_id = data["related_project_id"]
    db.session.commit()
    return jsonify({"ok": True, "data": t.to_dict()})


@bp.route("/todos/<int:tid>/done", methods=["POST"])
@login_required
def done_todo(tid):
    _, my_name = _me()
    t = _get_my_todo(tid)
    if not t:
        return jsonify({"ok": False, "error": "待办不存在"}), 404
    if t.source == "system":
        return jsonify({"ok": False, "error": _SYSTEM_GUARD}), 400
    t.status = "已完成"
    t.done_at = _now()
    t.done_by = my_name
    db.session.commit()
    return jsonify({"ok": True, "data": t.to_dict()})


@bp.route("/todos/<int:tid>/reopen", methods=["POST"])
@login_required
def reopen_todo(tid):
    t = _get_my_todo(tid)
    if not t:
        return jsonify({"ok": False, "error": "待办不存在"}), 404
    if t.source == "system":
        return jsonify({"ok": False, "error": _SYSTEM_GUARD}), 400
    t.status = "待办"
    t.done_at = ""
    t.done_by = ""
    db.session.commit()
    return jsonify({"ok": True, "data": t.to_dict()})


@bp.route("/todos/<int:tid>", methods=["DELETE"])
@login_required
def delete_todo(tid):
    t = _get_my_todo(tid)
    if not t:
        return jsonify({"ok": False, "error": "待办不存在"}), 404
    if t.source == "system":
        return jsonify({"ok": False, "error": _SYSTEM_GUARD}), 400
    db.session.delete(t)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})
