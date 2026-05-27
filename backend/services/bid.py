from sqlalchemy import text
from models import db
from models.project import Project
from models.agency import Agency


def get_agency_name(code):
    if not code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return a.name if a else code


def list_bid_projects(role, agency_code=None, officer=None):
    """按角色返回开标管理项目列表，有开标时间的排前面。"""
    base = db.select(Project).where(
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None))
    )
    if role == "agency":
        base = base.where(Project.agency_code == agency_code)
    elif role == "officer":
        base = base.where(Project.officer == officer)

    # 有 bid_time 的排前，空的排后；相同时按 bid_time 升序
    base = base.order_by(
        text("(bid_time = '') ASC"),
        Project.bid_time.asc(),
    )
    rows = db.session.execute(base).scalars().all()
    result = []
    for p in rows:
        d = p.to_dict()
        d["agency_name"] = get_agency_name(p.agency_code)
        result.append(d)
    return result


def mark_bid(pid, value, role, agency_code_session, officer_session):
    """标记能否开标。仅 agency 和 officer 可操作。"""
    if role not in ("agency", "officer"):
        raise PermissionError("无权限标记")
    if value not in ("可开标", "流标"):
        raise ValueError("无效的标记值")
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    if role == "agency" and p.agency_code != agency_code_session:
        raise PermissionError("只能标记自己的项目")
    if role == "officer" and p.officer != officer_session:
        raise PermissionError("只能标记自己的项目")
    p.can_open = value
    db.session.commit()
