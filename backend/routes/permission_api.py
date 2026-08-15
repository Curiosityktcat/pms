from functools import wraps
from flask import Blueprint, request, session, jsonify
from routes.utils import login_required, ROLE_CN
from services.permission import (
    PERMISSION_CATALOG,
    get_role_perms,
    set_role_perms,
    is_admin_user,
    DEFAULT_ROLE_PERMS,
)

bp = Blueprint("permission", __name__, url_prefix="/api/permissions")

# 可配置权限的业务角色（admin 账号自身拥有全部，不在此列）
MANAGED_ROLES = ["assistant", "officer", "leader", "agency", "supervisor", "dept"]


def admin_required(f):
    """仅系统管理员账号可访问。"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"ok": False, "error": "未登录"}), 401
        if not is_admin_user(session["user"]):
            return jsonify({"ok": False, "error": "无权限"}), 403
        return f(*args, **kwargs)
    return wrapper


@bp.route("/matrix", methods=["GET"])
@admin_required
def matrix():
    """权限矩阵：菜单目录 + 各业务角色当前权限。"""
    return jsonify({
        "ok": True,
        "catalog": PERMISSION_CATALOG,
        "roles": [{"role": r, "role_cn": ROLE_CN.get(r, r)} for r in MANAGED_ROLES],
        "perms": {r: get_role_perms(r) for r in MANAGED_ROLES},
    })


@bp.route("/<role>", methods=["PUT"])
@admin_required
def update(role):
    """覆盖式设置某角色的权限。"""
    if role not in MANAGED_ROLES:
        return jsonify({"ok": False, "error": "未知角色"}), 400
    data = request.get_json(force=True) or {}
    keys = data.get("keys") or []
    if not isinstance(keys, list):
        return jsonify({"ok": False, "error": "keys 必须为数组"}), 400
    set_role_perms(role, keys)
    return jsonify({"ok": True, "perms": get_role_perms(role)})


@bp.route("/<role>/reset", methods=["POST"])
@admin_required
def reset(role):
    """恢复某角色的默认权限。"""
    if role not in MANAGED_ROLES:
        return jsonify({"ok": False, "error": "未知角色"}), 400
    set_role_perms(role, DEFAULT_ROLE_PERMS.get(role, []))
    return jsonify({"ok": True, "perms": get_role_perms(role)})
