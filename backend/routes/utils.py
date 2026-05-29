from functools import wraps
from flask import session, jsonify

ROLE_CN = {
    "assistant": "采购部助理",
    "officer": "项目经办人",
    "leader": "采购部负责人",
    "agency": "代理机构",
    "supervisor": "监督",
}


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"ok": False, "error": "未登录"}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    """仅系统管理员账号可访问（后台管理系统专用）。"""
    from services.permission import is_admin_user

    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"ok": False, "error": "未登录"}), 401
        if not is_admin_user(session["user"]):
            return jsonify({"ok": False, "error": "无权限"}), 403
        return f(*args, **kwargs)
    return wrapper
