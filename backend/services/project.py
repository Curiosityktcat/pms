import datetime
from sqlalchemy import text
from models import db
from models.project import Project
from models.agency import Agency
from services.numbering import decide, gen_number, M_SOLE, M_JINGJI

STATUSES = ["立项", "委托代理", "编制中", "审核中", "已发公告", "报名中", "开标", "已定标", "合同签订", "已归档"]


def get_agency_name(code):
    if not code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return a.name if a else code


def list_projects(role, agency_code=None, officer=None, show_deleted=False):
    """按角色过滤并返回项目列表（含 agency_name）。
    show_deleted=True 时只返回已软删除的项目。
    """
    deleted_filter = (Project.is_deleted == 1) if show_deleted else db.or_(
        Project.is_deleted == 0, Project.is_deleted.is_(None)
    )

    if role == "agency":
        stmt = (
            db.select(Project)
            .where(Project.agency_code == agency_code)
            .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
            .where(deleted_filter)
            .order_by(Project.id.desc())
        )
    elif role == "officer":
        stmt = (
            db.select(Project)
            .where(Project.officer == officer)
            .where(deleted_filter)
            .order_by(Project.is_draft.desc(), Project.id.desc())
        )
    else:
        stmt = (
            db.select(Project)
            .where(deleted_filter)
            .order_by(Project.is_draft.desc(), Project.id.desc())
        )

    rows = db.session.execute(stmt).scalars().all()
    result = []
    for p in rows:
        d = p.to_dict()
        d["agency_name"] = get_agency_name(p.agency_code)
        result.append(d)
    return result


def _parse_amount(amount_raw, is_unit_price):
    if is_unit_price:
        return None
    try:
        return float(amount_raw)
    except (ValueError, TypeError):
        return None


def create_project(data, created_by, display_name):
    """
    创建项目（草稿或正式立项）。
    返回 (Project, number_or_None)。
    """
    now = datetime.datetime.now().isoformat(timespec="seconds")
    action = data.get("action", "submit")
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")

    method = (data.get("method") or "").strip()
    is_unit_price = bool(data.get("is_unit_price", False))
    amount_raw = data.get("amount", "")
    agency_code = (data.get("agency_code") or "").strip()
    officer = (data.get("officer") or display_name).strip()

    category = (data.get("category") or "").strip()
    year = (data.get("year") or str(datetime.datetime.now().year) + "年").strip()

    common = dict(
        name=name, method=method,
        round=int(data.get("round") or 1),
        demand_dept=(data.get("demand_dept") or "").strip(),
        manage_dept=(data.get("manage_dept") or "").strip(),
        officer=officer,
        content=(data.get("content") or "").strip(),
        category=category, year=year,
        created_by=created_by, created_at=now, updated_at=now,
    )

    if action == "draft":
        p = Project(
            number="", amount=_parse_amount(amount_raw, is_unit_price) or 0,
            line="", agency_code=agency_code, status="草稿", is_draft=1,
            **common,
        )
        db.session.add(p)
        db.session.commit()
        return p, None

    # 正式立项
    if not method:
        raise ValueError("请选择采购方式")
    amount = _parse_amount(amount_raw, is_unit_price)
    if not is_unit_price and amount is None:
        raise ValueError("请填写金额或勾选招单价")
    sole_use_agency = data.get("sole_use_agency", "")
    sole = (sole_use_agency == "yes") if method == M_SOLE else None
    use_agency, line = decide(method, amount, is_unit_price, sole)
    if use_agency and not agency_code:
        raise ValueError("走代理机构的项目必须选择代理机构")
    number = gen_number(use_agency, agency_code if use_agency else None)
    p = Project(
        number=number, amount=(amount if amount else 0), line=line,
        agency_code=agency_code if use_agency else "",
        bid_time=(data.get("bid_time") or "").strip(),
        status="立项", is_draft=0,
        **common,
    )
    db.session.add(p)
    db.session.commit()
    return p, number


def get_project(pid, role, agency_code_session, officer_session):
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    _check_read_perm(p, role, agency_code_session, officer_session)
    return p


def update_project(pid, data, role, agency_code_session, officer_session):
    """
    更新项目（普通保存 或 草稿→正式立项）。
    返回 (Project, number_or_None)。
    """
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    _check_write_perm(p, role, agency_code_session, officer_session)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    is_draft = bool(p.is_draft)
    action = data.get("action", "save")

    if is_draft and action == "submit":
        return _submit_draft(p, data, now)

    # 普通保存
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    p.name = name
    p.method = (data.get("method") or p.method).strip()
    p.demand_dept = (data.get("demand_dept") or "").strip()
    p.manage_dept = (data.get("manage_dept") or "").strip()
    p.officer = (data.get("officer") or "").strip()
    p.content = (data.get("content") or "").strip()
    p.bid_time = (data.get("bid_time") or "").strip()
    if "round" in data:
        p.round = int(data.get("round") or 1)
    if data.get("category"):
        p.category = data["category"].strip()
    if data.get("year"):
        p.year = data["year"].strip()
    if not is_draft:
        new_status = data.get("status") or ""
        if new_status in STATUSES:
            p.status = new_status
        # 已正式立项后允许更换代理机构：走代理（线 C）项目换代理机构时重新生成编号
        if "agency_code" in data:
            new_agency = (data.get("agency_code") or "").strip()
            use_agency = (p.line == "C")
            if use_agency:
                if not new_agency:
                    raise ValueError("走代理的项目必须选择代理机构")
                if new_agency != (p.agency_code or ""):
                    p.agency_code = new_agency
                    p.number = gen_number(True, new_agency)
    p.updated_at = now
    db.session.commit()
    return p, None


def _submit_draft(p, data, now):
    name = (data.get("name") or "").strip()
    if not name:
        raise ValueError("项目名称不能为空")
    method = (data.get("method") or "").strip()
    is_unit_price = bool(data.get("is_unit_price", False))
    amount_raw = data.get("amount", "")
    agency_code = (data.get("agency_code") or "").strip()
    sole_use_agency = data.get("sole_use_agency", "")
    amount = _parse_amount(amount_raw, is_unit_price)
    if not is_unit_price and amount is None:
        raise ValueError("请填写金额或勾选招单价")
    sole = (sole_use_agency == "yes") if method == M_SOLE else None
    use_agency, line = decide(method, amount, is_unit_price, sole)
    if use_agency and not agency_code:
        raise ValueError("走代理必须选代理机构")
    number = gen_number(use_agency, agency_code if use_agency else None)
    p.number = number
    p.name = name
    p.amount = amount if amount else 0
    p.line = line
    p.method = method
    p.demand_dept = (data.get("demand_dept") or "").strip()
    p.manage_dept = (data.get("manage_dept") or "").strip()
    p.agency_code = agency_code if use_agency else ""
    p.officer = (data.get("officer") or "").strip()
    p.content = (data.get("content") or "").strip()
    p.bid_time = (data.get("bid_time") or "").strip()
    p.category = (data.get("category") or p.category or "").strip()
    p.year = (data.get("year") or p.year or "").strip()
    if "round" in data:
        p.round = int(data.get("round") or 1)
    p.status = "立项"
    p.is_draft = 0
    p.updated_at = now
    db.session.commit()
    return p, number


def delete_project(pid, role, agency_code_session, officer_session):
    """软删除：标记 is_deleted=1，不物理删除。"""
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    if role == "agency":
        raise PermissionError("代理机构无权删除项目")
    if role == "officer" and p.officer != officer_session:
        raise PermissionError("无权删除此项目")
    p.is_deleted = 1
    p.deleted_at = datetime.datetime.now().isoformat(timespec="seconds")
    db.session.commit()


def restore_project(pid, role, agency_code_session, officer_session):
    """恢复软删除的项目。"""
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    if not p.is_deleted:
        raise ValueError("该项目未被删除")
    if role == "agency":
        raise PermissionError("代理机构无权恢复项目")
    if role == "officer" and p.officer != officer_session:
        raise PermissionError("无权恢复此项目")
    p.is_deleted = 0
    p.deleted_at = ""
    db.session.commit()


def _check_read_perm(p, role, agency_code_session, officer_session):
    if role == "agency" and p.agency_code != agency_code_session:
        raise PermissionError("无权查看此项目")
    if role == "officer" and p.officer != officer_session:
        raise PermissionError("无权查看此项目")


def _check_write_perm(p, role, agency_code_session, officer_session):
    if role == "agency" and p.agency_code != agency_code_session:
        raise PermissionError("无权编辑此项目")
    if role == "officer" and p.officer != officer_session:
        raise PermissionError("无权编辑此项目")
    if role in ("assistant", "leader"):
        raise PermissionError("助理/负责人暂无编辑权限")
