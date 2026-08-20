import datetime
from sqlalchemy import text
from models import db
from models.project import Project
from models.agency import Agency
from services.numbering import decide, gen_number, parse_agency_choice, M_SOLE, M_JINGJI
from services import project_number as pnum

STATUSES = ["立项", "委托代理", "编制中", "审核中", "已发公告", "报名中", "开标", "已定标", "合同签订", "已归档"]


def get_agency_name(code):
    if not code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return a.name if a else code


def get_agency_detail(code):
    """返回代理机构详细信息字典（name/legal_rep/phone/address），供前端预填。"""
    if not code:
        return {"agency_name": "", "agency_legal_rep": "", "agency_phone": "", "agency_address": ""}
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return {
        "agency_name":      a.name      if a else code,
        "agency_legal_rep": a.legal_rep if a else "",
        "agency_phone":     a.phone     if a else "",
        "agency_address":   a.address   if a else "",
    }


_EMPTY_AGENCY = {"agency_name": "", "agency_legal_rep": "",
                 "agency_phone": "", "agency_address": ""}


def _agency_map():
    """一次性把全部代理机构读成 {code: 详情字典}。

    代理机构总共十几家，而项目有几百个——逐项目查是 N+1（profile 显示占了
    /api/projects 近 7 成耗时）。这里一次查完，循环里查字典即可。"""
    rows = db.session.execute(
        db.select(Agency.code, Agency.name, Agency.legal_rep,
                  Agency.phone, Agency.address)).all()
    return {r.code: {"agency_name": r.name or r.code,
                     "agency_legal_rep": r.legal_rep or "",
                     "agency_phone": r.phone or "",
                     "agency_address": r.address or ""} for r in rows}


def list_projects(role, agency_code=None, officer=None, show_deleted=False, dept_code=None):
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
    elif role in ("dept", "dept_manage", "dept_demand"):
        # 归口科室账号：本科室归口 ∪ 本科室提需求的项目，草稿不给看。
        # 科室名可能改过（设备科→医学装备部），故按别名展开成名字集合匹配。
        from services import dept as _dept_svc
        _names = _dept_svc.dept_names(dept_code or "")
        stmt = (
            db.select(Project)
            .where(db.or_(Project.manage_dept.in_(_names),
                          Project.demand_dept.in_(_names))
                   if _names else db.false())
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
    _agencies = _agency_map()   # 循环外一次查完，避免 N+1
    result = []
    for p in rows:
        d = p.to_dict()
        # 原来这里逐项目 get_agency_detail(code) → N+1；现在查内存字典
        if p.agency_code:
            d.update(_agencies.get(p.agency_code)
                     or {**_EMPTY_AGENCY, "agency_name": p.agency_code})
        else:
            d.update(_EMPTY_AGENCY)
        result.append(d)

    # 按编号里的年月倒序（新的在前）。不能再按 id 排——历史项目是后补进系统的，
    # id 完全不反映实际发生顺序（2024 年的项目 id 反而比 2026 年的大）。
    # 草稿仍然置顶，编号读不出时间的沉到最后。
    result.sort(key=lambda d: (int(d.get("is_draft") or 0),
                               pnum.sort_key(d.get("number"))), reverse=True)
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
    sole = parse_agency_choice(method, data.get("use_agency") or data.get("sole_use_agency", ""))
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
    # 走代理项目立项即进入采购流程：建第一轮，使其能出现在「5.1 采购需求确认」等
    # 按 current_stage 筛选的列表里（阶段引擎需至少一条轮次记录才能定位到 demand_confirm）。
    if use_agency:
        from models.procurement_round import ProcurementRound
        import datetime as _dt
        db.session.add(ProcurementRound(
            project_id=p.id, round_number=1, demand_confirmed=0, doc_confirmed=0,
            status="进行中", created_at=_dt.datetime.now().isoformat(timespec="seconds")))
        p.round = 1
        db.session.commit()
    return p, number


def get_project(pid, role, agency_code_session, officer_session):
    p = db.session.get(Project, pid)
    if not p:
        raise ValueError("项目不存在")
    _check_read_perm(p, role, agency_code_session, officer_session)
    return p


def _entered_process(p):
    """项目是否已进入采购流程（进入后立项内容应锁定）：
    院内竞选/单一来源——已建采购轮次（到「采购需求确认」这一步）即锁；
    院内询价/议价/紧急采购——已发出询/议价函即锁。
    """
    from models.procurement_round import ProcurementRound
    from models.inquiry_letter import InquiryLetter
    if (p.method or "") in ("院内竞选", "院内单一来源采购"):
        return db.session.execute(
            db.select(ProcurementRound.id).filter_by(project_id=p.id).limit(1)
        ).first() is not None
    return db.session.execute(
        db.select(InquiryLetter.id).filter_by(project_id=p.id).limit(1)
    ).first() is not None


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

    # 已进入采购流程的项目：冻结立项核心内容（名称/采购方式/采购内容），
    # 避免流程过半再改需求。金额本就只在草稿提交时确定、立项后不可改。
    if not is_draft and _entered_process(p):
        changed = (
            ("name" in data and name != (p.name or ""))
            or ("method" in data and (data.get("method") or "").strip() != (p.method or ""))
            or ("content" in data and (data.get("content") or "").strip() != (p.content or ""))
        )
        if changed:
            raise ValueError("项目已进入采购流程，立项内容（名称/采购方式/采购内容）不可修改")

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
    amount = _parse_amount(amount_raw, is_unit_price)
    if not is_unit_price and amount is None:
        raise ValueError("请填写金额或勾选招单价")
    sole = parse_agency_choice(method, data.get("use_agency") or data.get("sole_use_agency", ""))
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
