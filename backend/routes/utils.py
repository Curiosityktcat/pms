from functools import wraps
from flask import session, jsonify

ROLE_CN = {
    "assistant": "采购部助理",
    "pd_assistant": "采购部助理",
    "officer": "项目经办人",
    "leader": "采购部负责人",
    "agency": "代理机构",
    "supervisor": "监督",
    "dept": "归口科室",
    "dept_manage": "归口管理科室",
    "dept_demand": "需求科室",
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
    from services.dept_scope import is_dept_role
    if is_dept_role(role):
        # 科室只看本科室（归口或需求）的项目。注意本函数对不认识的角色是
        # 「默认放行」的，新角色必须在这里显式收口，否则会从各子表接口漏看全部。
        from services import dept as _dept_svc
        _names = _dept_svc.dept_names(session.get("dept_code", ""))
        if not _names:
            return False
        return (proj.manage_dept or "") in _names or (proj.demand_dept or "") in _names
    return True


_RDWEB_FALLBACK_USER = "13029144451"
_RDWEB_FALLBACK_PASS = "whywhy123"


class RdwebNoAccount(RuntimeError):
    """当前操作人没有自己的 rd-web 执行账号。"""


def get_rdweb_creds(display_name: str = "", *, strict: bool = True) -> tuple[str, str]:
    """根据 PMS 用户姓名查对应的 rd-web 账号（owner=display_name, usage=执行）。

    **查不到就报错，绝不回退到别人的账号。**
    原来找不到会静默退回系统默认账号（那是黄新博的号），后果是：代理机构提交合同
    触发的推送、以及任何没配账号的人的推送，在 rd-web 上全都显示成黄新博干的
    （2026-08-18 用户实测发现，推送日志里推送人赫然是「四川三盈招标代理有限公司」）。
    以他人身份在审批系统里提交单据是不能接受的，宁可推不动也不能推错人。

    strict=False 只留给确实该用系统账号的后台任务（如公告抓取），业务推送一律 strict。
    """
    from models.project_distribution import RdwebAccount
    from models import db
    name = (display_name or "").strip()
    if name:
        row = db.session.execute(
            db.select(RdwebAccount).filter_by(owner=name, usage="执行")
        ).scalar_one_or_none()
        if row and row.phone and row.password:
            return row.phone, row.password
    if strict:
        who = f"「{name}」" if name else "当前登录账号"
        raise RdwebNoAccount(
            f"{who}还没有配 rd-web 执行账号，不能替别人推送。"
            "请在「2. 采购项目分发 → rd-web 账号」里配好本人的账号后重试。"
        )
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
