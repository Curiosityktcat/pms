"""科室账号访问既有业务接口时的统一数据范围。

这里刻意只认识 session 里的科室码：如果允许调用方传科室码，改一个查询参数
就能越过科室边界。非科室角色返回不受限，让既有采购部、经办人和代理机构逻辑
继续按原口径工作。
"""
from flask import abort, jsonify, make_response, session

from models import db
from models.project import Project
from services.dept import dept_names

DEPT_ROLES = ("dept", "dept_manage", "dept_demand")
WRITABLE_PERMS = {
    "procurement-demand-gov", "internal-bid-demand", "procurement-demand-sole",
    "procurement-demand-inquiry", "procurement-demand-emergency",
}


def is_dept_role(role=None) -> bool:
    """是否为科室类角色；保留 dept 是为了迁移脚本执行前存量账号仍受同一闸门约束。"""
    return (session.get("role") if role is None else role) in DEPT_ROLES


def current_dept_code() -> str:
    """返回当前科室账号绑定的科室码；其它角色不启用这层范围。"""
    if not is_dept_role():
        return ""
    return session.get("dept_code", "") or ""


def _project_scope_clause():
    """本科室项目的 SQL 条件；空/错误科室码有意收口为 false。"""
    names = dept_names(current_dept_code())
    dept_match = (
        db.or_(Project.manage_dept.in_(names), Project.demand_dept.in_(names))
        if names else db.false()
    )
    return db.and_(
        dept_match,
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
        db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
    )


def _visible_projects_stmt():
    """本科室可见项目 id 子查询，供非项目实体按 project_id 追溯。"""
    return (
        db.select(Project.id)
        .where(_project_scope_clause())
    )


def visible_project_ids() -> set | None:
    """返回科室可见项目 id；None 表示当前角色不受本过滤器限制。"""
    if not is_dept_role():
        return None
    return set(db.session.execute(_visible_projects_stmt()).scalars())


def scope_projects(stmt):
    """给 Project 查询加本科室范围，非科室角色原样返回。"""
    if not is_dept_role():
        return stmt
    return stmt.where(_project_scope_clause())


def scope_by_project(stmt, model):
    """给含 project_id 的模型查询加本科室范围。

    用子查询而不是先取 id 集合，确保列表始终在 SQL 层完成隔离；普通业务记录的
    project_id 为空时不可见，只有需求草稿按本科室的 demand_dept 额外放行。
    """
    if not is_dept_role():
        return stmt
    project_match = model.project_id.in_(_visible_projects_stmt())
    # 需求编制记录在立项前没有 project_id；此时必须按需求科室字段收口，否则科室既
    # 看不到自己刚建的草稿，也可能因调用方另写列表逻辑而出现两套隔离口径。
    if hasattr(model, "demand_dept"):
        names = dept_names(current_dept_code())
        return stmt.where(db.or_(project_match, model.demand_dept.in_(names)) if names else db.false())
    return stmt.where(project_match)


def assert_can_view_project(pid):
    """科室账号越界访问单个项目时直接抛 403。"""
    if not is_dept_role():
        return
    if pid is None or pid not in visible_project_ids():
        abort(make_response(jsonify({"ok": False, "error": "无权查看该项目"}), 403))


def assert_can_write_demand(demand_dept, project_id=None):
    """科室只能写本科室提出的需求；归口关联不能扩大需求编制的写范围。"""
    if not is_dept_role():
        return
    if (demand_dept or "").strip() not in dept_names(current_dept_code()):
        abort(make_response(jsonify({"ok": False, "error": "只能新建或修改本科室的需求"}), 403))


def assert_has_writable_perm(perm_key):
    """科室写需求同时受角色权限矩阵约束，管理员撤权后不能只靠前端隐藏。"""
    if not is_dept_role():
        return
    from services.permission import get_user_perms
    perms = get_user_perms(session.get("user", ""), session.get("role", ""))
    if perm_key not in WRITABLE_PERMS or perm_key not in perms:
        abort(make_response(jsonify({"ok": False, "error": "科室账号在本环节只有查看权限"}), 403))
