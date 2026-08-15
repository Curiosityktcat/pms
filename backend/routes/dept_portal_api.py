"""科室门户：归口科室自助查看本科室的项目进度与资料。

为什么单开一个 /api/dept/* 命名空间，而不是给科室角色发已有的菜单权限：
现有若干列表接口（如 archive.list_archive、routes.utils.can_view_project）是
「按角色减法」写的——认识 officer/agency 就过滤，遇到不认识的角色默认放行全部。
给新角色发老权限，等于要逐个路由去审计"默认放行"，漏一个就是整库泄露。
这里反过来做加法：科室角色只有 dept-portal 一个权限，本文件每个端点都先过
_scoped_project()，拿不到就 403。多写几十行代理，换的是「漏写=看不见」而不是
「漏写=全看见」。

可见范围：归口科室(manage_dept) 命中 ∪ 需求科室(demand_dept) 命中，草稿与已删除除外。
门户全部只读，不提供任何写操作。
"""
import os

from flask import Blueprint, jsonify, request, send_file, session

from models import db
from models.contract import Contract
from models.procurement_plan import ProcurementPlan
from models.project import Project
from routes.utils import login_required
from services import dept as dept_svc
from services.project_progress import build_progress, stage_map

bp = Blueprint("dept_portal", __name__, url_prefix="/api/dept")

# 采购部内部角色：可以借用门户视角看任意科室（他们本来就看得到全部项目），
# 用于「站在科室的角度检查他们能看到什么」。科室角色只能看自己那一个。
_OVERSEER_ROLES = ("assistant", "pd_assistant", "leader", "supervisor")

_UPLOADS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
_KIND_SUBDIR = {
    "demand":        "procurement_doc",
    "doc":           "procurement_doc",
    "review_result": "project_review",
    "result":        "procurement_result",
    "award_notice":  "procurement_result",
}


def _is_admin():
    from services.permission import is_admin_user
    return is_admin_user(session.get("user", ""))


def _current_dept_code():
    """本次请求要看哪个科室。科室账号锁死在自己科室，采购部角色可用 ?dept= 指定。"""
    role = session.get("role", "")
    if role in ("dept", "dept_manage", "dept_demand"):
        return session.get("dept_code", "") or ""
    if role in _OVERSEER_ROLES or _is_admin():
        return (request.args.get("dept") or "").strip()
    return ""


def _scope_names():
    """本次请求可见的科室名字集合。空集合 = 什么都看不到（有意为之）。"""
    code = _current_dept_code()
    return dept_svc.dept_names(code) if code else []


def _visible_stmt(names):
    return (
        db.select(Project)
        .where(db.or_(Project.manage_dept.in_(names), Project.demand_dept.in_(names)))
        .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
        .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
    )


def _scoped_project(pid):
    """取项目并校验属于本科室。返回 (project, error_response)。"""
    names = _scope_names()
    if not names:
        return None, (jsonify({"ok": False, "error": "未绑定科室"}), 403)
    p = db.session.get(Project, pid)
    if not p:
        return None, (jsonify({"ok": False, "error": "项目不存在"}), 404)
    if (p.manage_dept or "") not in names and (p.demand_dept or "") not in names:
        return None, (jsonify({"ok": False, "error": "无权查看该项目"}), 403)
    if p.is_deleted or p.is_draft:
        return None, (jsonify({"ok": False, "error": "无权查看该项目"}), 403)
    return p, None


# 阶段码 → 科室看得懂的说法。取值见 services.project_progress._stage_for，
# 科室不关心内部谁该点哪个按钮，只关心「走到哪一步了」。
_STAGE_CN = {
    "demand_confirm": "待确认采购需求",
    # 询/议价走的是另一条线（见 project_progress 的 inquiry_out）
    "inquiry":        "询价函待发出",
    "review":         "询价响应待评审",
    "contract":       "已定标，待签合同",
    "doc_confirm":    "采购文件编制中",
    "announce":       "待挂采购公告",
    "bid_open":       "已挂网，待开标",
    "round_failed":   "本轮流标，已重新招标",
    "result":         "已开标，待确认采购结果",
    "done":           "结果已确认，合同收尾",
}
_STAGE_ORDER = ["demand_confirm", "inquiry", "doc_confirm", "announce", "bid_open",
                "review", "round_failed", "result", "contract", "done"]
_ARCHIVED = "archived"


def _stage_cn(code):
    if code == _ARCHIVED:
        return "已归档"
    return _STAGE_CN.get(code, code or "进行中")


@bp.route("/me", methods=["GET"])
@login_required
def me():
    """当前视角的科室信息 + 可选科室列表（采购部角色用来切换）。"""
    code = _current_dept_code()
    d = dept_svc.get_dept(code) if code else None
    role = session.get("role", "")
    payload = {
        "role": role,
        "dept": d.to_dict() if d else None,
        "can_switch": role in _OVERSEER_ROLES or _is_admin(),
    }
    if payload["can_switch"]:
        payload["depts"] = [x.to_dict() for x in dept_svc.list_depts()]
    return jsonify({"ok": True, "data": payload})


@bp.route("/overview", methods=["GET"])
@login_required
def overview():
    """本科室概览：项目总数、在办/已归档、按阶段分布、按年度分布。"""
    names = _scope_names()
    if not names:
        return jsonify({"ok": False, "error": "未绑定科室"}), 403
    rows = db.session.execute(_visible_stmt(names)).scalars().all()
    smap = stage_map([p.id for p in rows]) if rows else {}

    by_stage, by_year = {}, {}
    ongoing = archived = 0
    for p in rows:
        # 已归档的项目不再按流程阶段归类——它已经走完了，归档就是它的终态。
        is_arch = (p.status or "") == "已归档"
        st = _ARCHIVED if is_arch else ((smap.get(p.id) or {}).get("current_stage") or "")
        by_stage[st] = by_stage.get(st, 0) + 1
        y = (p.year or "").replace("年", "") or "未填"
        by_year[y] = by_year.get(y, 0) + 1
        if is_arch:
            archived += 1
        else:
            ongoing += 1

    order = _STAGE_ORDER + [_ARCHIVED]
    stages = [{"stage": s, "stage_cn": _stage_cn(s), "count": by_stage[s]}
              for s in order if s in by_stage]
    stages += [{"stage": s, "stage_cn": _stage_cn(s), "count": c}
               for s, c in by_stage.items() if s not in order]

    return jsonify({"ok": True, "data": {
        "dept": dept_svc.dept_display(_current_dept_code()),
        "total": len(rows),
        "ongoing": ongoing,
        "archived": archived,
        "stages": stages,
        "years": sorted(({"year": y, "count": c} for y, c in by_year.items()),
                        key=lambda x: x["year"], reverse=True),
    }})


@bp.route("/projects", methods=["GET"])
@login_required
def list_projects():
    """本科室项目列表（只读）。支持 year / keyword / stage / 是否含已归档 过滤。"""
    names = _scope_names()
    if not names:
        return jsonify({"ok": False, "error": "未绑定科室"}), 403

    rows = db.session.execute(_visible_stmt(names)).scalars().all()
    smap = stage_map([p.id for p in rows]) if rows else {}

    year = (request.args.get("year") or "").strip()
    kw = (request.args.get("keyword") or "").strip()
    stage = (request.args.get("stage") or "").strip()
    include_archived = request.args.get("archived", "1") != "0"

    out = []
    for p in rows:
        info = smap.get(p.id) or {}
        is_arch = (p.status or "") == "已归档"
        st = _ARCHIVED if is_arch else (info.get("current_stage") or "")
        if not include_archived and is_arch:
            continue
        if year and (p.year or "").replace("年", "") != year:
            continue
        if stage and st != stage:
            continue
        if kw and kw not in (p.name or "") and kw not in (p.number or ""):
            continue
        out.append({
            "id": p.id,
            "number": p.number or "",
            "name": p.name or "",
            "amount": p.amount,
            "method": p.method or "",
            "status": p.status or "",
            "manage_dept": p.manage_dept or "",
            "demand_dept": p.demand_dept or "",
            "bid_time": p.bid_time or "",
            "year": (p.year or "").replace("年", ""),
            "round": info.get("current_round") or p.round or 1,
            "current_stage": st,
            "stage_cn": _stage_cn(st),
            "archived": is_arch,
        })

    from services import project_number as pnum
    out.sort(key=lambda d: pnum.sort_key(d.get("number")), reverse=True)
    return jsonify({"ok": True, "data": out, "total": len(out)})


@bp.route("/projects/<int:pid>", methods=["GET"])
@login_required
def project_detail(pid):
    """项目详情：科室关心的字段 + 合同摘要。不含代理考核等采购部内部信息。"""
    p, err = _scoped_project(pid)
    if err:
        return err
    contracts = db.session.execute(
        db.select(Contract).filter_by(project_id=pid).order_by(Contract.id)
    ).scalars().all()
    plan = db.session.execute(
        db.select(ProcurementPlan).filter_by(project_id=pid)
    ).scalars().first()
    return jsonify({"ok": True, "data": {
        "id": p.id,
        "number": p.number or "",
        "name": p.name or "",
        "amount": p.amount,
        "method": p.method or "",
        "status": p.status or "",
        "content": p.content or "",
        "manage_dept": p.manage_dept or "",
        "demand_dept": p.demand_dept or "",
        "bid_time": p.bid_time or "",
        "year": (p.year or "").replace("年", ""),
        "round": p.round or 1,
        "plan": {"id": plan.id, "name": plan.name, "plan_number": plan.plan_number or ""} if plan else None,
        "contracts": [{
            "id": c.id,
            "contract_number": c.contract_number or "",
            "contract_name": c.contract_name or "",
            "package_no": c.package_no or "",
            "supplier_name": c.supplier_name or "",
            "amount": c.amount,
            "amount_text": c.amount_text or "",
            "sign_date": c.sign_date or "",
            "service_start": c.service_start or "",
            "service_end": c.service_end or "",
            "status": c.status or "",
        } for c in contracts],
    }})


@bp.route("/projects/<int:pid>/progress", methods=["GET"])
@login_required
def project_progress(pid):
    """逐轮逐节点进度，直接复用采购部那套 build_progress，口径完全一致。"""
    p, err = _scoped_project(pid)
    if err:
        return err
    return jsonify({"ok": True, "data": build_progress(p)})


@bp.route("/projects/<int:pid>/tree", methods=["GET"])
@login_required
def project_tree(pid):
    """资料树：该项目按轮次组织的归档要件。"""
    p, err = _scoped_project(pid)
    if err:
        return err
    from services.archive_print import list_archive_tree
    return jsonify({"ok": True, "data": _rewrite_urls(list_archive_tree(p), pid)})


@bp.route("/projects/<int:pid>/item", methods=["GET"])
@login_required
def project_item(pid):
    """预览/下载单个归档要件（现生成的 docx）。"""
    p, err = _scoped_project(pid)
    if err:
        return err
    try:
        rno = int(request.args.get("round", 1))
    except (TypeError, ValueError):
        rno = 1
    from services.archive_print import build_item, _cn_round
    try:
        buf, name = build_item(p, rno, request.args.get("kind", ""))
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500
    if buf is None:
        return jsonify({"ok": False, "error": "该要件不存在或暂不可生成"}), 404
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=request.args.get("download") == "1",
        download_name=f"{p.number or p.name}-{_cn_round(rno)}-{name}.docx",
    )


@bp.route("/projects/<int:pid>/attachment/<int:aid>", methods=["GET"])
@login_required
def project_attachment(pid, aid):
    """预览/下载各模块上传的真实文件。"""
    p, err = _scoped_project(pid)
    if err:
        return err
    from models.procurement_doc_attachment import ProcurementDocAttachment
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    subdir = _KIND_SUBDIR.get(att.kind)
    if not subdir:
        return jsonify({"ok": False, "error": "不支持的附件类型"}), 404
    path = os.path.join(_UPLOADS, subdir, str(pid), att.saved_name or "")
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    if request.args.get("download") == "1":
        return send_file(path, as_attachment=True,
                         download_name=att.original_name or att.saved_name)
    from services.office_convert import send_preview
    return send_preview(path, att.original_name or att.saved_name)


@bp.route("/plans", methods=["GET"])
@login_required
def list_plans():
    """本科室在采购计划池里的计划条目，以及是否已关联到实际采购项目。"""
    code = _current_dept_code()
    names = dept_svc.dept_names(code) if code else []
    if not names:
        return jsonify({"ok": False, "error": "未绑定科室"}), 403
    rows = db.session.execute(
        db.select(ProcurementPlan)
        .where(db.or_(ProcurementPlan.dept.in_(names),
                      ProcurementPlan.demand_dept.in_(names)))
        .order_by(ProcurementPlan.id)
    ).scalars().all()
    year = (request.args.get("year") or "").strip()
    out = []
    for r in rows:
        if year and str(r.year or "") != year:
            continue
        proj = db.session.get(Project, r.project_id) if r.project_id else None
        out.append({
            "id": r.id,
            "year": r.year,
            "name": r.name or "",
            "dept": r.dept or "",
            "demand_dept": r.demand_dept or "",
            "budget": r.budget,
            "method": r.method or "",
            "status": r.status or "",
            "deadline": r.deadline or "",
            "project": {"id": proj.id, "number": proj.number or "", "name": proj.name or ""} if proj else None,
        })
    return jsonify({"ok": True, "data": out, "total": len(out)})


@bp.route("/contracts", methods=["GET"])
@login_required
def list_contracts():
    """本科室项目的合同一览——报销时最常要查的就是这张表。"""
    names = _scope_names()
    if not names:
        return jsonify({"ok": False, "error": "未绑定科室"}), 403
    pids = [p.id for p in db.session.execute(_visible_stmt(names)).scalars()]
    if not pids:
        return jsonify({"ok": True, "data": [], "total": 0})
    projects = {p.id: p for p in db.session.execute(
        db.select(Project).where(Project.id.in_(pids))).scalars()}
    rows = db.session.execute(
        db.select(Contract).where(Contract.project_id.in_(pids)).order_by(Contract.id.desc())
    ).scalars().all()
    out = []
    for c in rows:
        p = projects.get(c.project_id)
        out.append({
            "id": c.id,
            "project_id": c.project_id,
            "project_number": (p.number if p else "") or "",
            "project_name": (p.name if p else "") or "",
            "contract_number": c.contract_number or "",
            "contract_name": c.contract_name or "",
            "package_no": c.package_no or "",
            "supplier_name": c.supplier_name or "",
            "amount": c.amount,
            "amount_text": c.amount_text or "",
            "sign_date": c.sign_date or "",
            "service_start": c.service_start or "",
            "service_end": c.service_end or "",
            "status": c.status or "",
        })
    return jsonify({"ok": True, "data": out, "total": len(out)})


def _rewrite_urls(tree, pid):
    """把 /api/archive/<pid>/... 换成 /api/dept/projects/<pid>/...

    档案树是采购部那边生成的，地址自然指向 /api/archive；科室角色被闸门挡在
    /api/dept/* 之外，不换地址就点不开。门户侧 item / attachment / approval-record
    三个端点齐全且都过 _scoped_project，所以整段前缀替换是安全的。
    """
    old = "/api/archive/%d/" % pid
    new = "/api/dept/projects/%d/" % pid

    def fix(v):
        if not isinstance(v, str):
            return v
        v = v.replace(old, new)
        # 询议价项目的要件挂在询价函下，地址是 /api/inquiries/<lid>/...；
        # 这棵树是单个项目的，里面的询价函必然属于它，整段改写是安全的。
        v = v.replace("/api/inquiries/", "/api/dept/inquiries/")
        return v

    out = []
    for folder in tree or []:
        items = []
        for it in (folder.get("items") or []):
            items.append({k: fix(v) for k, v in it.items()})
        out.append({**folder, "items": items})
    return out


@bp.route("/projects/<int:pid>/approval-record", methods=["GET"])
@login_required
def project_approval_record(pid):
    """《审批过程记录表》：科室常问「这个项目在谁那儿卡了多久」，这张表就是答案。"""
    p, err = _scoped_project(pid)
    if err:
        return err
    from services.approval_record_word import build
    buf, name = build(p)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True, download_name=name,
    )


def _scoped_letter(lid):
    """取询价函并校验它挂的项目属于本科室。"""
    from models.inquiry_letter import InquiryLetter
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return None, None, (jsonify({"ok": False, "error": "询价函不存在"}), 404)
    p, err = _scoped_project(letter.project_id)
    if err:
        return None, None, err
    return letter, p, None


def _inquiry_word(lid, as_attachment):
    letter, proj, err = _scoped_letter(lid)
    if err:
        return err
    from services.inquiry_word import generate_inquiry_word
    buf = generate_inquiry_word(letter, proj.name or "", proj.number or "", proj.officer or "")
    title = (letter.title or "%s邀请函" % letter.type).replace("/", "-")
    return send_file(
        buf, as_attachment=as_attachment, download_name="%s.docx" % title,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@bp.route("/inquiries/<int:lid>/word", methods=["GET"])
@login_required
def dept_inquiry_word(lid):
    """询/议价邀请函（下载）。"""
    return _inquiry_word(lid, True)


@bp.route("/inquiries/<int:lid>/word/preview", methods=["GET"])
@login_required
def dept_inquiry_word_preview(lid):
    """询/议价邀请函（预览）。"""
    return _inquiry_word(lid, False)


def _inquiry_att(lid, aid, download):
    letter, _proj, err = _scoped_letter(lid)
    if err:
        return err
    from routes.inquiry_api import _inquiry_attachment_path
    att, path = _inquiry_attachment_path(lid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    if download:
        return send_file(path, as_attachment=True, download_name=att.filename)
    from services.office_convert import send_preview
    return send_preview(path, att.filename)


@bp.route("/inquiries/<int:lid>/attachments/<int:aid>/download", methods=["GET"])
@login_required
def dept_inquiry_attachment_download(lid, aid):
    return _inquiry_att(lid, aid, True)


@bp.route("/inquiries/<int:lid>/attachments/<int:aid>/preview", methods=["GET"])
@login_required
def dept_inquiry_attachment_preview(lid, aid):
    return _inquiry_att(lid, aid, False)
