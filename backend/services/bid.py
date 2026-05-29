import re
from datetime import datetime
from sqlalchemy import text
from models import db
from models.project import Project
from models.agency import Agency
from models.announcement import Announcement


def get_agency_name(code):
    if not code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return a.name if a else code


def _parse_cn_deadline(s):
    """解析中文日期时间，支持全角冒号 '：' 和半角冒号 ':' 两种格式"""
    if not s:
        return None
    # 兼容全角冒号 ：(U+FF1A) 和半角冒号 :(U+003A)
    m = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2})[：:](\d{2})', s)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def list_bid_projects(role, agency_code=None, officer=None):
    """只返回正在挂网进行中（已发布且开标时间未到）的项目，附带公告轮次"""
    now = datetime.now()

    # 获取所有已确认的采购公告
    confirmed_anns = db.session.execute(
        db.select(Announcement)
        .where(Announcement.status == "已确认")
        .where(Announcement.ann_type == "procurement")
    ).scalars().all()

    # 筛选出开标时间未到的公告，收集项目ID及对应公告信息
    active_project_ids = set()
    active_ann_map: dict = {}   # project_id -> {ann_id, round_number, response_deadline}
    for ann in confirmed_anns:
        deadline = _parse_cn_deadline(ann.response_deadline)
        if deadline and deadline > now:
            active_project_ids.add(ann.project_id)
            # 如同一项目有多轮有效公告，取轮次最高的
            prev = active_ann_map.get(ann.project_id)
            if prev is None or ann.round_number > prev["round_number"]:
                active_ann_map[ann.project_id] = {
                    "ann_id": ann.id,
                    "round_number": ann.round_number,
                    "response_deadline": ann.response_deadline,
                }

    if not active_project_ids:
        return []

    # 查询这些项目
    base = (
        db.select(Project)
        .where(Project.id.in_(active_project_ids))
        .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
        .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
    )

    if role == "agency":
        base = base.where(Project.agency_code == agency_code)
    # officer / leader / assistant 均可查看所有项目

    base = base.order_by(
        text("(bid_time = '') ASC"),
        Project.bid_time.asc(),
    )

    rows = db.session.execute(base).scalars().all()
    result = []
    for p in rows:
        d = p.to_dict()
        d["agency_name"] = get_agency_name(p.agency_code)
        ann_info = active_ann_map.get(p.id, {})
        d["ann_id"] = ann_info.get("ann_id")
        d["ann_round_number"] = ann_info.get("round_number", 1)
        d["ann_deadline"] = ann_info.get("response_deadline", p.bid_time or "")
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
