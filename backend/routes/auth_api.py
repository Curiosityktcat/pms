import os
import requests
from flask import Blueprint, request, session, jsonify
from services.auth import check_login, change_password
from services.permission import get_user_perms
from routes.utils import login_required, ROLE_CN

bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# ── 登录滑块验证：须持一次性通行令牌（PMS_CAPTCHA_ON=0 可临时关闭以防锁死）──
_CAPTCHA_URL = os.environ.get("CAPTCHA_URL", "http://127.0.0.1:3060")
_CAPTCHA_ON = os.environ.get("PMS_CAPTCHA_ON", "1") == "1"


def _captcha_ok(token):
    if not _CAPTCHA_ON:
        return True
    if not token:
        return False
    try:
        r = requests.post(f"{_CAPTCHA_URL}/verify_token",
                          json={"token": token, "action": "pms_login"}, timeout=6)
        return r.status_code == 200 and r.json().get("ok")
    except Exception:
        return False


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    # agent-hxb service-account：项目管家 Agent 用固定 service 账号(密码仍必须正确)
    # 从内网发起时跳过人机滑块——滑块是反机器人手段，这是受信任的内网自动化，
    # 账号可随时在后台停用以吊销。仅豁免滑块，绝不豁免密码。用户已明确授权(2026-07)。
    # 一人一个 agent 盒子 → service 账号是一组（agent-hxb / agent-zyj / …）。
    # 只豁免滑块，密码照验、且必须来自内网；停用账号即整体吊销该盒子。
    _agent_accts = {u.strip() for u in os.environ.get(
        "PMS_AGENT_USERS", "agent-hxb,agent-zyj").split(",") if u.strip()}
    _agent_accts.add(os.environ.get("PMS_AGENT_USER", "agent-hxb"))
    _ip = request.remote_addr or ""
    _internal = _ip.startswith(("127.", "10.", "192.168.", "172."))
    _skip_captcha = username in _agent_accts and _internal
    if not _skip_captcha and not _captcha_ok(data.get("captcha_token")):
        return jsonify({"ok": False, "error": "请先完成滑块验证", "need_captcha": True}), 400
    password = data.get("password") or ""
    user = check_login(username, password)
    if not user:
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    # 启用带有效期的会话：配合 PERMANENT_SESSION_LIFETIME 实现 30 分钟空闲过期
    session.permanent = True
    session["user"] = user.username
    session["role"] = user.role
    session["display_name"] = user.display_name
    session["agency_code"] = user.agency_code or ""
    session["dept_code"] = user.dept_code or ""
    session["must_change_pw"] = int(getattr(user, "must_change_pw", 0) or 0)
    from services.dept import dept_display
    return jsonify({"ok": True, "user": {
        "username": user.username,
        "role": user.role,
        "role_cn": ROLE_CN.get(user.role, user.role),
        "display_name": user.display_name,
        "agency_code": user.agency_code or "",
        "dept_code": user.dept_code or "",
        "dept_name": dept_display(user.dept_code),
        "perms": get_user_perms(user.username, user.role),
        "is_admin": user.username == "admin",
        # 批量建号发下去的是一次性密码，没改之前前端要强制弹改密框
        "must_change_pw": int(getattr(user, "must_change_pw", 0) or 0),
    }})


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"ok": True})


@bp.route("/me", methods=["GET"])
@login_required
def me():
    from services.dept import dept_display
    return jsonify({"ok": True, "user": {
        "username": session["user"],
        "role": session["role"],
        "role_cn": ROLE_CN.get(session["role"], session["role"]),
        "display_name": session["display_name"],
        "dept_code": session.get("dept_code", ""),
        "dept_name": dept_display(session.get("dept_code", "")),
        "agency_code": session.get("agency_code", ""),
        "perms": get_user_perms(session["user"], session["role"]),
        "is_admin": session["user"] == "admin",
        "must_change_pw": int(session.get("must_change_pw", 0) or 0),
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
    session["must_change_pw"] = 0          # 闸门立刻放开，不用重新登录
    return jsonify({"ok": True, "message": msg})
