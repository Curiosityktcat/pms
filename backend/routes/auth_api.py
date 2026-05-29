from flask import Blueprint, request, session, jsonify
from services.auth import check_login, change_password
from services.permission import get_user_perms
from routes.utils import login_required, ROLE_CN

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    user = check_login(username, password)
    if not user:
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    session["user"] = user.username
    session["role"] = user.role
    session["display_name"] = user.display_name
    session["agency_code"] = user.agency_code or ""
    return jsonify({"ok": True, "user": {
        "username": user.username,
        "role": user.role,
        "role_cn": ROLE_CN.get(user.role, user.role),
        "display_name": user.display_name,
        "agency_code": user.agency_code or "",
        "perms": get_user_perms(user.username, user.role),
        "is_admin": user.username == "admin",
    }})


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route("/me", methods=["GET"])
@login_required
def me():
    return jsonify({"ok": True, "user": {
        "username": session["user"],
        "role": session["role"],
        "role_cn": ROLE_CN.get(session["role"], session["role"]),
        "display_name": session["display_name"],
        "agency_code": session.get("agency_code", ""),
        "perms": get_user_perms(session["user"], session["role"]),
        "is_admin": session["user"] == "admin",
    }})


@bp.route("/chpwd", methods=["POST"])
@login_required
def chpwd():
    data = request.get_json(force=True) or {}
    old = data.get("old") or ""
    n1 = data.get("n1") or ""
    n2 = data.get("n2") or ""
    if not n1 or n1 != n2:
        return jsonify({"ok": False, "error": "两次新密码不一致或为空"}), 400
    ok, msg = change_password(session["user"], old, n1)
    if not ok:
        return jsonify({"ok": False, "error": msg}), 400
    return jsonify({"ok": True, "message": msg})
