import re
from datetime import datetime
from sqlalchemy import text
from models import db
from models.project import Project
from models.agency import Agency
from models.announcement import Announcement
from models.procurement_round import ProcurementRound
from models.package import Package
from models.round_package import RoundPackage
from services.dept_scope import scope_by_project, scope_projects


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
    """返回已发布采购公告、且本轮尚未判定开标结果的项目，附带公告轮次。

    注意：不按开标时间过滤——开标恰在响应截止之后进行，截止后仍需能判可开标/流标。
    判定完成（can_open_status='已确认'，即可开标或流标已定）的项目会离开本列表。
    """
    # 获取所有已确认的采购公告
    confirmed_anns = db.session.execute(
        scope_by_project(db.select(Announcement), Announcement)
        .where(Announcement.status == "已确认")
        .where(Announcement.ann_type == "procurement")
    ).scalars().all()

    # 收集项目ID及对应公告信息（同一项目多轮公告取轮次最高的）
    active_project_ids = set()
    active_ann_map: dict = {}   # project_id -> {ann_id, round_number, response_deadline}
    for ann in confirmed_anns:
        active_project_ids.add(ann.project_id)
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
    base = scope_projects(base)

    if role == "agency":
        base = base.where(Project.agency_code == agency_code)
    # officer / leader / assistant 均可查看所有项目

    base = base.order_by(
        text("(bid_time = '') ASC"),
        Project.bid_time.asc(),
    )

    rows = db.session.execute(base).scalars().all()

    # 各项目当前（最新）轮次对象：公告所属轮若已被流标推进过（当前轮 > 公告轮），
    # 说明该轮已流标结束，不再出现在开标管理。
    latest_round = {}
    for r in db.session.execute(
        db.select(ProcurementRound)
        .where(ProcurementRound.project_id.in_(active_project_ids))
        .order_by(ProcurementRound.round_number.asc())
    ).scalars().all():
        latest_round[r.project_id] = r   # 升序遍历，最终留下最大轮

    result = []
    for p in rows:
        ann_info = active_ann_map.get(p.id, {})
        ann_round = ann_info.get("round_number", 1)
        rnd = latest_round.get(p.id)
        if rnd and rnd.round_number > ann_round:
            continue  # 该公告所属轮已流标结束
        # bucket：active=进行中（待判定/可开标但开标时间未过）；opened=已开标（归档）
        bucket = "active"
        if rnd and rnd.can_open_status == "已确认":
            if rnd.can_open != "可开标":
                continue  # 流标已确认 → 随轮次推进离开开标管理
            # 「可开标」开标当天仍留在进行中（可复核/生成授权函）；
            # 开标时间过了（次日起）或无从判断截止时间，归入「已开标」归档
            ddl = _parse_cn_deadline(
                ann_info.get("response_deadline") or p.bid_time or "")
            if ddl is None or datetime.now().date() > ddl.date():
                bucket = "opened"
        d = p.to_dict()
        d["bucket"] = bucket
        d["agency_name"] = get_agency_name(p.agency_code)
        d["ann_id"] = ann_info.get("ann_id")
        d["ann_round_number"] = ann_round
        d["ann_deadline"] = ann_info.get("response_deadline", p.bid_time or "")
        # 本轮开标标记状态（供 UI 渲染 可开标 / 流标待确认 / 流标）
        d["can_open"] = (rnd.can_open if rnd else "") or ""
        d["can_open_status"] = (rnd.can_open_status if rnd else "") or ""
        d["can_open_reason"] = (rnd.can_open_reason if rnd else "") or ""
        d["can_open_by"] = (rnd.can_open_by if rnd else "") or ""
        d["can_open_confirmed_by"] = (rnd.can_open_confirmed_by if rnd else "") or ""
        result.append(d)
    return result


def _markable_round(pid, role, agency_code_session, officer_session,
                    require_officer=False, require_agency=False):
    """权限校验 + 返回当前轮（必须本轮已发布采购公告）。"""
    if role not in ("agency", "officer"):
        raise PermissionError("无权限操作")
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    if role == "agency" and p.agency_code != agency_code_session:
        raise PermissionError("只能操作自己的项目")
    if role == "officer" and p.officer != officer_session:
        raise PermissionError("只能操作自己的项目")
    if require_agency and role != "agency":
        raise PermissionError("仅代理机构可提交流标")
    if require_officer and role != "officer":
        raise PermissionError("仅经办人可确认")

    rnd = db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=pid)
        .order_by(ProcurementRound.round_number.desc())
    ).scalars().first()
    # 安全闸：必须当前轮已发布采购公告，避免流标开新轮后误操作到后面的轮次。
    has_ann = rnd and db.session.execute(
        db.select(Announcement.id).filter_by(
            project_id=pid, ann_type="procurement", round_number=rnd.round_number,
        ).where(Announcement.status == "已确认")
    ).first()
    if not rnd or not has_ann:
        raise ValueError("当前轮尚未发布采购公告，无法标记开标")
    return p, rnd


def mark_can_open(pid, role, agency_code_session, officer_session):
    """可开标：单步生效（代理或经办人均可）。"""
    p, rnd = _markable_round(pid, role, agency_code_session, officer_session)
    if rnd.can_open_status == "已确认":
        raise ValueError("本轮开标结果已确认，不能重复标记")
    if rnd.can_open_status == "待确认":
        raise ValueError("本轮存在待确认的流标，请先撤回再标记可开标")
    now = datetime.now().isoformat(timespec="seconds")
    actor = officer_session or agency_code_session or ""
    rnd.can_open = "可开标"
    rnd.can_open_status = "已确认"
    rnd.can_open_reason = ""
    rnd.can_open_at = now
    rnd.can_open_by = actor
    rnd.can_open_confirmed_by = actor
    rnd.can_open_confirmed_at = now
    p.can_open = "可开标"
    db.session.commit()


def propose_bid_fail(pid, reason, role, agency_code_session, officer_session):
    """流标第一步：仅代理机构可提交流标 + 原因（状态「待确认」，经办人确认后才结束本轮）。

    经办人不能直接发起流标——报名/供应商数量由代理机构掌握，须由代理提交、经办人确认，
    两步制衡。前端对经办人显示置灰按钮并说明。
    """
    p, rnd = _markable_round(pid, role, agency_code_session, officer_session,
                             require_agency=True)
    if rnd.can_open_status == "已确认":
        raise ValueError("本轮开标结果已确认，无法再提交流标")
    reason = (reason or "").strip()
    if not reason:
        raise ValueError("请填写流标原因")
    rnd.can_open = "流标"
    rnd.can_open_status = "待确认"
    rnd.can_open_reason = reason
    rnd.can_open_at = datetime.now().isoformat(timespec="seconds")
    rnd.can_open_by = officer_session or agency_code_session or ""
    p.can_open = "流标待确认"   # 镜像位仅供列表提示
    db.session.commit()


def confirm_bid_fail(pid, role, agency_code_session, officer_session):
    """流标第二步：经办人确认流标 → 结束本轮、自动开下一轮。"""
    p, rnd = _markable_round(pid, role, agency_code_session, officer_session,
                             require_officer=True)
    if rnd.can_open != "流标" or rnd.can_open_status != "待确认":
        raise ValueError("没有待确认的流标")
    rnd.can_open_status = "已确认"
    rnd.can_open_confirmed_by = officer_session or ""
    rnd.can_open_confirmed_at = datetime.now().isoformat(timespec="seconds")
    p.can_open = "流标"
    _advance_round_on_bid_fail(p, rnd)
    db.session.commit()


def revoke_bid_fail(pid, role, agency_code_session, officer_session):
    """撤回待确认的流标（代理或经办人均可，仅限尚未经办人确认时）。"""
    p, rnd = _markable_round(pid, role, agency_code_session, officer_session)
    if rnd.can_open != "流标" or rnd.can_open_status != "待确认":
        raise ValueError("没有待确认的流标可撤回")
    rnd.can_open = ""
    rnd.can_open_status = ""
    rnd.can_open_reason = ""
    rnd.can_open_by = ""
    rnd.can_open_at = ""
    p.can_open = ""
    db.session.commit()


def _advance_round_on_bid_fail(project, rnd):
    """开标流标：结束本轮，把本轮全部在产包滚入新一轮，重置确认状态（幂等）。

    与采购结果「废标包开下一轮」(_apply_result_to_cycle) 同源；区别是流标整体作废，
    本轮所有「进行中」的包全部进入下一轮。
    """
    if rnd is None or rnd.status != "进行中":
        return
    later = db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=project.id)
        .where(ProcurementRound.round_number > rnd.round_number)
    ).first()
    if later:
        return  # 已开过下一轮，不重复

    now = datetime.now().isoformat(timespec="seconds")
    round_pkgs = db.session.execute(
        db.select(RoundPackage).filter_by(round_id=rnd.id)
    ).scalars().all()

    rnd.status = "已结束"
    next_no = rnd.round_number + 1
    new_round = ProcurementRound(project_id=project.id, round_number=next_no,
                                 status="进行中", created_at=now)
    db.session.add(new_round)
    db.session.flush()
    for rp in round_pkgs:
        pkg = db.session.get(Package, rp.package_id)
        if pkg and pkg.status == "进行中":
            db.session.add(RoundPackage(round_id=new_round.id, package_id=pkg.id, result="待定"))

    project.round = next_no
    # 进入下一轮：需重新做采购需求/文件确认，开标缓存清零（镜像位）
    project.demand_confirmed = 0
    project.demand_confirmed_by = ""
    project.demand_confirmed_at = ""
    project.doc_confirmed = 0
    project.doc_confirmed_by = ""
    project.doc_confirmed_at = ""
    project.can_open = ""
