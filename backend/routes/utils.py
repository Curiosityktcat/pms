from functools import wraps
from flask import session, jsonify

ROLE_CN = {
    "assistant": "采购部助理",
    "pd_assistant": "采购部助理",
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


def can_view_project(proj):
    """数据级项目可见性：代理只看本机构、经办人只看本人项目，其余角色（助理/负责人/管理员/监督）看全部。

    与 services/project.list_projects 的过滤口径保持一致，供按项目展开的子表
    （询/议价函、询议价评审等）做同样的归属隔离。
    """
    if proj is None:
        return False
    role = session.get("role", "")
    if role == "agency":
        return proj.agency_code == session.get("agency_code", "")
    if role == "officer":
        return proj.officer == session.get("display_name", "")
    return True


_RDWEB_FALLBACK_USER = "13029144451"
_RDWEB_FALLBACK_PASS = "whywhy123"


def get_rdweb_creds(display_name: str = "") -> tuple[str, str]:
    """根据 PMS 用户姓名查对应的 rd-web 账号（owner=display_name, usage=执行）。
    找不到时回退到系统默认账号。"""
    from models.project_distribution import RdwebAccount
    from models import db
    if display_name:
        row = db.session.execute(
            db.select(RdwebAccount).filter_by(owner=display_name, usage="执行")
        ).scalar_one_or_none()
        if row and row.phone and row.password:
            return row.phone, row.password
    return _RDWEB_FALLBACK_USER, _RDWEB_FALLBACK_PASS


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
