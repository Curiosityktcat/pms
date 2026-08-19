from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
import json, os
from models import db
from models.procurement_demand import ProcurementDemand
from models.project import Project
from models.agency import Agency
from routes.utils import login_required
from services.permission import is_admin_user
from services import upload_relay
from services.dept_scope import assert_can_write_demand, assert_has_writable_perm, is_dept_role, scope_by_project

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'emergency')

bp = Blueprint("procurement_demand", __name__, url_prefix="/api/procurement-demands")

FLOW = ["草稿", "待分发", "已分发", "已立项"]
DEMAND_PERMS = {
    "gov": "procurement-demand-gov", "sole_source": "procurement-demand-sole",
    "inquiry": "procurement-demand-inquiry", "emergency": "procurement-demand-emergency",
}


def _scope_ok(demand) -> bool:
    """采购需求归属：本人创建(created_by) 或被指派(assigned_officer)；
    助理/负责人/管理员全部；代理机构不可见。"""
    role = session.get("role", "")
    if role in ("assistant", "leader") or is_admin_user(session.get("user", "")):
        return True
    if role == "agency":
        return False
    me = session.get("display_name", "")
    return me != "" and me in ((demand.created_by or ""), (demand.assigned_officer or ""))


def _scoped(did):
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return None, (jsonify({"ok": False, "error": "不存在"}), 404)
    if is_dept_role():
        assert_has_writable_perm(DEMAND_PERMS.get(demand.demand_type, ""))
        assert_can_write_demand(demand.demand_dept, demand.project_id)
        return demand, None
    if not _scope_ok(demand):
        return None, (jsonify({"ok": False, "error": "无权访问该采购需求"}), 403)
    return demand, None


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _agency_name(code):
    if not code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return a.name if a else code


def _enrich(d: ProcurementDemand):
    data = d.to_dict()
    data["agency_name"] = _agency_name(d.assigned_agency_code)
    if d.project_id:
        p = db.session.get(Project, d.project_id)
        data["project_number"] = p.number if p else ""
    else:
        data["project_number"] = ""
    return data


# ── 列表（按角色 + 需求类型过滤） ─────────────────────────────────
@bp.route("", methods=["GET"])
@login_required
def list_demands():
    role = session["role"]
    name = session.get("display_name", "")
    status_filter  = request.args.get("status", "")
    demand_type    = request.args.get("demand_type", "")  # gov/competition/sole_source/inquiry

    q = scope_by_project(
        db.select(ProcurementDemand), ProcurementDemand
    ).order_by(ProcurementDemand.id.desc())

    if role == "agency":
        return jsonify({"ok": True, "data": []})

    if role == "officer":
        q = q.where(
            db.or_(
                db.and_(
                    ProcurementDemand.assigned_officer == name,
                    ProcurementDemand.status.in_(["已分发", "已立项"])
                ),
                db.and_(
                    ProcurementDemand.created_by == name,
                    ProcurementDemand.status == "草稿"
                )
            )
        )

    if status_filter:
        q = q.where(ProcurementDemand.status == status_filter)
    if demand_type:
        q = q.where(ProcurementDemand.demand_type == demand_type)

    rows = db.session.execute(q).scalars().all()
    return jsonify({"ok": True, "data": [_enrich(r) for r in rows]})


# ── 创建（草稿） ─────────────────────────────────────────────────
@bp.route("", methods=["POST"])
@login_required
def create_demand():
    if session["role"] == "agency":
        return jsonify({"ok": False, "error": "无权限"}), 403
    data = request.get_json(force=True) or {}
    assert_has_writable_perm(DEMAND_PERMS.get(data.get("demand_type"), ""))
    assert_can_write_demand(data.get("demand_dept"))
    now = _now()
    items = data.pop("items", [])
    # 去掉不属于模型的字段
    allowed = {c.name for c in ProcurementDemand.__table__.columns}
    filtered = {k: v for k, v in data.items()
                if k in allowed and k not in ("id", "project_id", "created_at", "updated_at", "items_json", "items",
                                               "status", "assigned_officer", "assigned_agency_code",
                                               "dispatched_by", "dispatched_at")}
    demand = ProcurementDemand(
        status="草稿",
        created_by=session.get("display_name", ""),
        created_at=now,
        updated_at=now,
        items_json=json.dumps(items, ensure_ascii=False),
        **filtered,
    )
    db.session.add(demand)
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 获取单条 ────────────────────────────────────────────────────
@bp.route("/<int:did>", methods=["GET"])
@login_required
def get_demand(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 更新（仅草稿/已分发状态可编辑正文） ──────────────────────────
@bp.route("/<int:did>", methods=["PUT"])
@login_required
def update_demand(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项的需求不可修改"}), 400

    data = request.get_json(force=True) or {}
    if "demand_dept" in data:
        assert_can_write_demand(data.get("demand_dept"))
    items = data.pop("items", None)
    if items is not None:
        demand.items_json = json.dumps(items, ensure_ascii=False)

    locked = {"id", "project_id", "created_by", "created_at", "items_json", "items",
              "status", "assigned_officer", "assigned_agency_code", "dispatched_by", "dispatched_at"}
    for k, v in data.items():
        if hasattr(demand, k) and k not in locked:
            setattr(demand, k, v)
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 删除（仅草稿） ───────────────────────────────────────────────
@bp.route("/<int:did>", methods=["DELETE"])
@login_required
def delete_demand(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status != "草稿":
        return jsonify({"ok": False, "error": "只有草稿状态的需求可以删除"}), 400
    db.session.delete(demand)
    db.session.commit()
    return jsonify({"ok": True})


# ── 提交（草稿 → 待分发） ────────────────────────────────────────
@bp.route("/<int:did>/submit", methods=["POST"])
@login_required
def submit_demand(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status != "草稿":
        return jsonify({"ok": False, "error": "只有草稿状态可以提交"}), 400
    if not (demand.project_name or "").strip():
        return jsonify({"ok": False, "error": "请先填写采购需求名称"}), 400
    demand.status = "待分发"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交，等待采购部分发"})


# ── 撤回（待分发 → 草稿） ────────────────────────────────────────
@bp.route("/<int:did>/recall", methods=["POST"])
@login_required
def recall_demand(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status != "待分发":
        return jsonify({"ok": False, "error": "只有待分发状态可以撤回"}), 400
    demand.status = "草稿"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回为草稿"})


# ── 分发（待分发 → 已分发，助理/负责人操作） ────────────────────
@bp.route("/<int:did>/dispatch", methods=["POST"])
@login_required
def dispatch_demand(did):
    if session["role"] not in ("assistant", "leader"):
        return jsonify({"ok": False, "error": "仅采购部助理/负责人可分发"}), 403
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status != "待分发":
        return jsonify({"ok": False, "error": "只有待分发状态可以分发"}), 400

    data = request.get_json(force=True) or {}
    officer = (data.get("assigned_officer") or "").strip()
    if not officer:
        return jsonify({"ok": False, "error": "请指定经办人"}), 400

    demand.assigned_officer = officer
    demand.assigned_agency_code = (data.get("assigned_agency_code") or "").strip()
    demand.dispatched_by = session.get("display_name", "")
    demand.dispatched_at = _now()
    demand.status = "已分发"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": f"已分发给 {officer}"})


# ── 退回（已分发 → 待分发，助理操作） ─────────────────────────
@bp.route("/<int:did>/return", methods=["POST"])
@login_required
def return_demand(did):
    if session["role"] not in ("assistant", "leader"):
        return jsonify({"ok": False, "error": "仅采购部助理/负责人可退回"}), 403
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status != "已分发":
        return jsonify({"ok": False, "error": "只有已分发状态可以退回"}), 400
    demand.assigned_officer = ""
    demand.assigned_agency_code = ""
    demand.status = "待分发"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已退回"})


# ── 立项（已分发 → 已立项，经办人操作）─────────────────────────
@bp.route("/<int:did>/create-project", methods=["POST"])
@login_required
def create_project_from_demand(did):
    """
    经办人确认立项：根据分发信息 + 表单数据创建正式采购项目，
    返回新建项目的信息。前端跳转到项目立项页面（已预填），
    实际 Project 由 project_api 创建；本接口只做校验 + 返回预填数据。
    """
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status != "已分发":
        return jsonify({"ok": False, "error": "只有已分发状态可以立项"}), 400
    if session["role"] != "officer":
        return jsonify({"ok": False, "error": "仅项目经办人可立项"}), 403

    # 返回预填数据供前端跳转到立项表单使用
    # gov 采购方式映射：预算采购方式字段 budget_method 优先，否则用通用 procurement_method
    if demand.demand_type == "gov":
        method_for_project = demand.budget_method or "院内竞选"
    else:
        method_for_project = demand.procurement_method or "院内竞选"

    return jsonify({
        "ok": True,
        "prefill": {
            "demand_id": demand.id,
            "demand_type": demand.demand_type,   # 传给立项表单用于判断是否归档
            "name": demand.project_name,
            "category": demand.category,
            "year": demand.year,
            "amount": demand.budget_amount if demand.budget_amount else None,
            "method": method_for_project,
            "agency_code": demand.assigned_agency_code,
            "demand_dept": demand.demand_dept,
            "manage_dept": demand.manage_dept,
            "content": demand.project_overview,
            "officer": session.get("display_name", ""),
        }
    })


# ── 标记已立项（由 project_api 在创建项目成功后调用） ──────────
@bp.route("/<int:did>/mark-approved", methods=["POST"])
@login_required
def mark_approved(did):
    """当 project_api 成功创建项目后，回调此接口把需求标记为已立项。"""
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    data = request.get_json(force=True) or {}
    project_id = data.get("project_id")
    demand.project_id = project_id
    demand.status = "已立项"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True})


# ── 生成 Word ─────────────────────────────────────────────────
@bp.route("/<int:did>/word", methods=["GET"])
@login_required
def generate_word(did):
    from services.procurement_demand_word import generate
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    try:
        buf, filename = generate(demand, project)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True, download_name=filename,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500


# ══════════════════════════════════════════════════════════════════
# 按模板出稿：成稿文件 ＝ 模板 ＋ 信息
#
# 老的 /word 是把版式写死在代码里的；这套改成用《2.2内江市第一人民医院采购需求表》
# 那份 Word 模板套打（按 procurement-doc-templates 的规矩改造过）。
# 好处是版式归文员管、改模板不用改代码，坏处是模板写错了要能当场看出来——
# 所以配了 /doc-status 告诉界面哪些占位符还空着。
# ══════════════════════════════════════════════════════════════════

@bp.route("/<int:did>/doc-status", methods=["GET"])
@login_required
def demand_doc_status(did):
    """出稿前的体检：模板在不在、还有哪些空着。界面上按这个提示人去补。"""
    from services import demand_doc
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    import os as _os
    if not _os.path.exists(demand_doc.TEMPLATE):
        return jsonify({"ok": False, "error": "还没配采购需求表模板"}), 404
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    ctx = demand_doc.build_context(demand, project)
    missing = demand_doc.missing_fields(ctx)
    total = len(demand_doc.load_fields())
    return jsonify({"ok": True, "data": {
        "total": total,
        "filled": total - len(missing),
        "missing": [{"name": m["name"], "label": m["label"], "kind": m["kind"]}
                    for m in missing],
    }})


@bp.route("/<int:did>/doc", methods=["GET"])
@login_required
def demand_doc_file(did):
    """出稿。?download=1 下载 Word，否则转 PDF 给右边的预览用。"""
    from services import demand_doc
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    try:
        buf, _missing = demand_doc.render(demand, project)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:                                   # noqa: BLE001
        # 模板语法错误在这儿必须说清楚，否则文员改完模板只看到「生成失败」
        return jsonify({"ok": False, "error": f"套打失败：{e}"[:300]}), 500

    name = (demand.project_name or f"采购需求{did}").strip()[:60]
    if request.args.get("download") == "1":
        return send_file(
            buf, as_attachment=True, download_name=f"{name}-采购需求表.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    # 预览：落个临时文件转 PDF（LibreOffice 只认路径）
    import os as _os
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="demanddoc_")
    src = _os.path.join(tmpdir, f"{name}.docx")
    with open(src, "wb") as fh:
        fh.write(buf.getvalue())
    # 必须转 PDF：这个响应是塞进 <iframe> 的，浏览器渲染不了 .docx。
    # send_preview 对新版 Office 默认发原文件，要显式要 PDF。
    from services.office_convert import to_pdf
    try:
        pdf = to_pdf(src)
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"ok": False,
                        "error": f"转 PDF 失败，预览用不了（可以先下载 Word 看）：{e}"[:300]}), 500
    return send_file(pdf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{name}-采购需求表.pdf")


# ══════════════════════════════════════════════════════════════════
# 采购需求模板库（⑩ 的第 1 条）
#
# 「很多项目都属于同一类型，大多数的内容都一样……每个经办人可以让其他人 COPY 过去，
#   或者是授权使用。」
# 存的不是 Word 文件，是**一份填好的需求信息**；套用就是拷进新需求，再改差异那几项。
# ══════════════════════════════════════════════════════════════════

# 默认存哪几个部分——他点名的：第三、六~十一。第一、二部分是这个项目独有的，
# 存进模板反而会把新项目的信息覆盖掉。
TPL_SECTIONS = ["第三部分", "第六部分", "第七部分", "第八部分",
                "第九部分", "第十部分", "第十一部分"]

# 每个部分对应哪些列。分包（第四~第八）整份存在 packages 里，不在这儿逐列列。
SECTION_FIELDS = {
    "第三部分": ["org_form", "budget_method", "procurement_method", "package_split",
                "is_multi_year", "sme_policy", "is_eco_product", "is_energy_save",
                "has_import_product", "is_govt_service", "is_info_system",
                "is_research_equip"],
    "第六部分": ["business_requirements"],
    "第七部分": ["qualification_requirements"],
    "第八部分": ["eval_method", "eval_price_score", "eval_tech_criteria",
                "eval_service_criteria"],
    "第九部分": ["contract_type", "contract_is_actual", "contract_period",
                "contract_location", "payment_terms", "acceptance_delivery",
                "warranty_terms", "ip_terms", "cost_risk_terms", "breach_terms",
                "other_contract_terms", "performance_bond_terms"],
    "第十部分": ["acceptance_org", "invite_other_supplier"],
    "第十一部分": [],
}


def _me():
    return session.get("display_name", "")


def _is_admin():
    from services.permission import is_admin_user
    return is_admin_user(session.get("user", ""))


@bp.route("/templates", methods=["GET"])
@login_required
def list_demand_templates():
    """我能用的模板：自己的 + 公开的 + 别人授权给我的。"""
    from models.demand_template import DemandTemplate as T
    me, adm = _me(), _is_admin()
    rows = db.session.execute(db.select(T).order_by(T.id.desc())).scalars().all()
    data = [t.to_dict(me, adm) for t in rows if t.can_use(me, adm)]
    dtype = (request.args.get("demand_type") or "").strip()
    if dtype:
        data = [x for x in data if not x["demand_type"] or x["demand_type"] == dtype]
    return jsonify({"ok": True, "data": data, "sections": TPL_SECTIONS})


@bp.route("/<int:did>/save-as-template", methods=["POST"])
@login_required
def save_as_template(did):
    """把这条需求存成模板。只存选中的那几个部分。"""
    from models.demand_template import DemandTemplate as T
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"ok": False, "error": "给模板起个名字，比如「医用耗材类·院内竞选」"}), 400
    sections = body.get("sections") or TPL_SECTIONS

    data = {}
    for sec in sections:
        for col in SECTION_FIELDS.get(sec, []):
            v = getattr(demand, col, None)
            if v not in (None, ""):
                data[col] = v
    # 分包整份带走（第四~第八部分都在里面）
    if body.get("with_packages", True):
        data["packages"] = getattr(demand, "packages_json", "") or "[]"

    row = T(name=name, note=(body.get("note") or "").strip(),
            demand_type=demand.demand_type or "",
            sections_json=json.dumps(sections, ensure_ascii=False),
            data_json=json.dumps(data, ensure_ascii=False),
            owner=_me(), shared=1 if body.get("shared") else 0,
            shared_with=",".join(body.get("shared_with") or []),
            created_at=_now(), updated_at=_now())
    db.session.add(row)
    db.session.commit()
    return jsonify({"ok": True, "data": row.to_dict(_me(), _is_admin()),
                    "message": f"已存为模板「{name}」，存了 {len(data)} 项内容"})


@bp.route("/<int:did>/apply-template/<int:tid>", methods=["POST"])
@login_required
def apply_demand_template(did, tid):
    """把模板套进这条需求。只覆盖模板里有的字段，其余不动。"""
    from models.demand_template import DemandTemplate as T
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项的需求不可修改"}), 400
    tpl = db.session.get(T, tid)
    if not tpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not tpl.can_use(_me(), _is_admin()):
        return jsonify({"ok": False,
                        "error": "这份模板没有对你开放，找它的主人授权"}), 403

    try:
        data = json.loads(tpl.data_json or "{}")
    except Exception:                                        # noqa: BLE001
        return jsonify({"ok": False, "error": "模板内容坏了，读不出来"}), 400

    applied = []
    for col, v in data.items():
        if col == "packages":
            demand.packages_json = v
            try:
                demand.package_count = len(json.loads(v or "[]")) or 1
            except Exception:                                # noqa: BLE001
                pass
            applied.append("分包（第四~第八部分）")
            continue
        if hasattr(demand, col):
            setattr(demand, col, v)
            applied.append(col)
    demand.updated_at = _now()
    tpl.use_count = (tpl.use_count or 0) + 1
    db.session.commit()
    return jsonify({"ok": True, "data": demand.to_dict() if hasattr(demand, "to_dict") else {},
                    "applied": applied,
                    "message": f"已套用模板「{tpl.name}」，覆盖了 {len(applied)} 项"})


@bp.route("/templates/<int:tid>", methods=["PUT", "DELETE"])
@login_required
def edit_demand_template(tid):
    """改名/授权/删除。只有主人（和管理员）能动。"""
    from models.demand_template import DemandTemplate as T
    tpl = db.session.get(T, tid)
    if not tpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not tpl.can_edit(_me(), _is_admin()):
        return jsonify({"ok": False, "error": "只有模板的主人能改它"}), 403
    if request.method == "DELETE":
        db.session.delete(tpl)
        db.session.commit()
        return jsonify({"ok": True, "message": "已删除"})
    body = request.get_json(silent=True) or {}
    if "name" in body:
        tpl.name = (body["name"] or "").strip() or tpl.name
    if "note" in body:
        tpl.note = body["note"] or ""
    if "shared" in body:
        tpl.shared = 1 if body["shared"] else 0
    if "shared_with" in body:
        tpl.shared_with = ",".join(body["shared_with"] or [])
    tpl.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": tpl.to_dict(_me(), _is_admin())})


@bp.route("/template-lint", methods=["POST"])
@login_required
def lint_uploaded_template():
    """上传 Word 模板时当场体检——不合格的当场列给做模板的人看。"""
    import os as _os
    import tempfile
    from services import template_lint, field_dict
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "没有收到文件"}), 400
    if not f.filename.lower().endswith(".docx"):
        return jsonify({"ok": False, "error": "请上传 .docx（Word 2007 以后的格式）"}), 400
    tmp = _os.path.join(tempfile.mkdtemp(prefix="tpllint_"), _os.path.basename(f.filename))
    f.save(tmp)
    known = [x["name"] for x in field_dict.load()]
    errors, warns, names = template_lint.lint(tmp, known)
    return jsonify({"ok": True, "data": {
        "errors": errors, "warnings": warns, "placeholders": names,
        "passed": not errors,
    }})


@bp.route("/field-dict", methods=["GET"])
@login_required
def field_dict_all():
    """字段字典：界面照它渲染条件字段。条件和联动都在这儿，前端不写业务判断。"""
    from services import field_dict as fd
    return jsonify({"ok": True, "data": fd.load()})


@bp.route("/field-dict/resolve", methods=["POST"])
@login_required
def field_dict_resolve():
    """按当前填的值算一遍：哪些该出现、哪些锁死成什么、哪些提示。

    前端每次改动调一次，界面就跟着变——判断逻辑只有后端一份，
    不会出现「界面允许填、出稿却被纠正」这种对不上的情况。
    """
    from services import field_dict as fd
    values = (request.get_json(silent=True) or {}).get("values") or {}
    fields = fd.load()
    eff, meta = fd.resolve(fields, values)
    return jsonify({"ok": True, "data": {
        "values": eff, "meta": meta, "errors": fd.validate(fields, values)}})


@bp.route("/doc-fields", methods=["GET"])
@login_required
def demand_doc_fields():
    """模板里有哪些占位符——界面上「信息」那一栏照这个分组显示。"""
    from services import demand_doc
    return jsonify({"ok": True, "data": demand_doc.load_fields()})


# ── Excel 模板下载 ────────────────────────────────────────────
@bp.route("/template/<dtype>", methods=["GET"])
@login_required
def download_template(dtype):
    allowed = {"gov", "competition", "sole_source", "inquiry", "emergency"}
    if dtype not in allowed:
        return jsonify({"ok": False, "error": "未知需求类型"}), 400
    from services.demand_excel import generate_template
    buf, filename = generate_template(dtype)
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


# ── Excel 导入解析 ────────────────────────────────────────────
@bp.route("/import-excel", methods=["POST"])
@login_required
def import_excel():
    file = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    dtype = request.form.get("demand_type", "competition")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    if not file.filename.lower().endswith(".xlsx"):
        return jsonify({"ok": False, "error": "仅支持 .xlsx 格式"}), 400
    from services.demand_excel import parse_excel
    try:
        result = parse_excel(dtype, file.read())
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": f"解析失败：{e}"}), 400


# ── 附件上传（紧急采购） ──────────────────────────────────────
@bp.route("/<int:did>/upload", methods=["POST"])
@login_required
def upload_attachment(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项，不可修改"}), 400
    file = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    from werkzeug.utils import secure_filename
    original = secure_filename(file.filename)
    ext = os.path.splitext(original)[1].lower()
    allowed = {".pdf", ".jpg", ".jpeg", ".png", ".docx", ".doc", ".xlsx", ".xls"}
    if ext not in allowed:
        return jsonify({"ok": False, "error": f"不支持的文件类型（{ext}）"}), 400
    save_name = f"em_{did}_{_now().replace(':', '-').replace('T', '_')}{ext}"
    save_path = os.path.join(UPLOAD_DIR, save_name)
    file.save(save_path)
    rel_path  = f"uploads/emergency/{save_name}"
    demand.attachment_path = rel_path
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "path": rel_path, "original_name": original})


# ── 附件下载 ──────────────────────────────────────────────────
@bp.route("/<int:did>/attachment", methods=["GET"])
@login_required
def download_attachment(did):
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if not demand.attachment_path:
        return jsonify({"ok": False, "error": "无附件"}), 404
    base = os.path.dirname(os.path.dirname(__file__))
    file_path = os.path.join(base, demand.attachment_path)
    if not os.path.exists(file_path):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    return send_file(file_path, as_attachment=True,
                     download_name=os.path.basename(demand.attachment_path))


# ── 可用代理机构列表（供分发时选择） ──────────────────────────
@bp.route("/agencies", methods=["GET"])
@login_required
def agencies():
    from models.agency import Agency
    rows = db.session.execute(db.select(Agency).filter_by(active=1)).scalars().all()
    return jsonify({"ok": True, "data": [{"code": a.code, "name": a.name} for a in rows]})
