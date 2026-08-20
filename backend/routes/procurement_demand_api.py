from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
import json, os, secrets
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

    # 缺件在**提交**这一步拦，保存不拦（黄新博 2026-08-20：
    # 「缺件后可以保存但是无法提交就行」）。填一半存着是常态，
    # 发给采购部之前才必须齐全。
    missing = _required_missing(demand)
    if missing:
        return jsonify({
            "ok": False, "error": "这几项必须填了才能提交：" + "、".join(missing[:8])
                                  + (f" 等 {len(missing)} 项" if len(missing) > 8 else ""),
            "missing": missing,
        }), 400

    demand.status = "待分发"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交，等待采购部分发"})


def _required_missing(demand):
    """提交前查缺件：返回缺的字段名（中文），空表示齐了。

    判据来自字段字典——哪些必填、哪些在当前条件下压根不出现，都由字典说了算，
    这里不另写一套（写两套迟早对不上）。
    """
    from services import demand_doc, field_dict
    fields = field_dict.load(demand_doc.dict_name_for(demand))
    if not fields:
        return []
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    ctx = demand_doc.build_context_for(demand, project)
    errs = field_dict.validate(fields, ctx)
    out = []
    for e in errs:
        if "必填" in e:
            name = e.split("「", 1)[-1].split("」", 1)[0] if "「" in e else e
            out.append(name)
    return out


@bp.route("/<int:did>/check", methods=["GET"])
@login_required
def check_demand(did):
    """提交前自检：缺哪些。界面上保存后提示一下，别等点了提交才知道。"""
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    missing = _required_missing(demand)
    return jsonify({"ok": True, "data": {
        "missing": missing, "can_submit": not missing,
        "name_ok": bool((demand.project_name or "").strip()),
    }})


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
    # 必须转 PDF：这个响应是塞进 <iframe> 的，浏览器渲染不了 .docx。
    # 按**内容指纹**缓存——填的信息没变，第二次预览直接给缓存，
    # 不再每次重跑 LibreOffice（原来每次 2.2 秒，因为缓存键带临时路径，一次都命中不了）。
    from services.office_convert import to_pdf_bytes
    try:
        pdf = to_pdf_bytes(buf.getvalue())
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"ok": False,
                        "error": f"转 PDF 失败，预览用不了（可以先下载 Word 看）：{e}"[:300]}), 500
    resp = send_file(pdf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{name}-采购需求表.pdf")
    # 内容变了 URL 上的 v 就变，所以可以放心让浏览器缓存一会儿
    resp.headers["Cache-Control"] = "private, max-age=60"
    return resp


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


# ══════════════════════════════════════════════════════════════════
# 采购需求 Agent（⑩ 的第 2 条）：上传资料 → 它读了给建议 → 人点采纳才落库
#
# 「只提建议，不直接落库」是有意为之：金额、编号、法条这类东西模型写错了
# 是要担责的，必须有人过一眼。每条建议都带原文依据，好核对。
# ══════════════════════════════════════════════════════════════════

AGENT_UPLOAD_DIR = os.path.join(
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")),
    "uploads", "demand_agent")
AGENT_EXT = {".pdf", ".doc", ".docx", ".jpg", ".jpeg", ".png", ".txt"}


def _agent_facts(did):
    """只读当前政府采购需求的事实；scope 已由调用接口先校验。"""
    from models.demand_agent_fact import DemandAgentFact as F
    return db.session.execute(
        db.select(F).filter_by(demand_id=did, demand_kind="gov").order_by(F.id)
    ).scalars().all()


def _save_agent_facts(did, updates, message_id, created_by):
    """落本轮新事实。经办人确认是最高优先级，模型和文档都不能覆盖。"""
    from models.demand_agent_fact import DemandAgentFact as F
    saved = []
    for item in updates or []:
        key = str(item.get("key") or "").strip()
        source = str(item.get("source") or "model")
        if not key or source not in ("user", "model", "document"):
            continue
        row = db.session.execute(db.select(F).filter_by(
            demand_id=did, demand_kind="gov", key=key)).scalar_one_or_none()
        if row and row.source == "user" and source != "user":
            continue
        if row is None:
            row = F(demand_id=did, demand_kind="gov", key=key)
            db.session.add(row)
        row.value = json.dumps(item.get("value"), ensure_ascii=False)
        row.source = source
        evidence = str(item.get("evidence") or "")
        if source == "user" and evidence == "经办人本轮回答":
            evidence = f"经办人 {_now()[:10]} 回答"
        elif source == "user" and evidence == "经办人本轮选择":
            evidence = f"经办人 {_now()[:10]} 选择"
        elif source == "user" and evidence.startswith("经办人本轮采纳 agent 建议："):
            evidence = evidence.replace("经办人本轮", f"经办人 {_now()[:10]}", 1)
        row.evidence = evidence[:500]
        row.message_id = message_id
        row.created_by = created_by if source == "user" else source
        row.created_at = _now()
        saved.append(row)
    return saved


def _chat_history_rows(rows):
    """给编排器的历史保留问题和附件名，模型才能把自由文本答案对回事实 key。"""
    return [{"role": m.role, "text": m.text,
             "material": getattr(m, "material", "") or "",
             "files": m.to_dict().get("files") or [],
             "suggestions": m.to_dict().get("suggestions") or {}}
            for m in rows]


@bp.route("/<int:did>/chat", methods=["GET"])
@login_required
def demand_chat_history(did):
    """这条需求和 Agent 的对话记录。下次打开还能看到上次聊到哪。"""
    from models.demand_chat import DemandChatMessage as M
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    rows = db.session.execute(
        db.select(M).filter_by(demand_id=did, demand_kind="gov").order_by(M.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [m.to_dict() for m in rows],
                    "facts": [f.to_dict() for f in _agent_facts(did)]})


@bp.route("/<int:did>/chat", methods=["POST"])
@login_required
def demand_chat_send(did):
    """发一条消息（可带文件），Agent 回一条。两条都落库。"""
    import tempfile
    from models.demand_chat import DemandChatMessage as M
    from services import demand_agent, demand_doc, field_dict

    demand, _serr = _scoped(did)
    if _serr:
        return _serr

    text = (request.form.get("text") or "").strip()
    files = [f for f in (request.files.getlist("file")
                         or request.files.getlist("files")) if f and f.filename]
    if not text and not files:
        return jsonify({"ok": False, "error": "说点什么，或者传个文件"}), 400

    # ── 存下附件并读出文字 ────────────────────────────────────────
    os.makedirs(os.path.join(AGENT_UPLOAD_DIR, str(did)), exist_ok=True)
    saved, paths = [], []
    for f in files:
        name = os.path.basename(f.filename)
        ext = os.path.splitext(name)[1].lower()
        if ext not in AGENT_EXT:
            saved.append({"name": name, "error": f"不支持 {ext or '无扩展名'}"})
            continue
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        fn = f"{stamp}_{secrets.token_hex(3)}{ext}"
        dst = os.path.join(AGENT_UPLOAD_DIR, str(did), fn)
        f.save(dst)
        paths.append((name, dst))
        saved.append({"name": name, "saved": fn})

    material, failed = demand_agent.read_files(paths)
    for item in saved:
        for msg in failed:
            if msg.startswith(item.get("name", "") + "："):
                item["error"] = msg.split("：", 1)[1]
    for item in saved:
        if not item.get("error") and item.get("saved"):
            item["chars"] = len(material) if len(paths) == 1 else None

    now = _now()
    me = session.get("display_name", "")
    umsg = M(demand_id=did, demand_kind="gov", role="user", text=text,
             files_json=json.dumps(saved, ensure_ascii=False),
             material=material,          # 后面几轮还要靠它记得传过什么
             created_by=me, created_at=now)
    db.session.add(umsg)
    db.session.commit()

    # ── 历史 + 锁定字段 ──────────────────────────────────────────
    rows = db.session.execute(
        db.select(M).filter_by(demand_id=did, demand_kind="gov").order_by(M.id)
    ).scalars().all()
    history = _chat_history_rows(rows[:-1])
    facts = [f.to_dict() for f in _agent_facts(did)]

    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    ctx = demand_doc.build_context_for(demand, project)
    fields = field_dict.load(demand_doc.dict_name_for(demand))
    locked = []
    if fields:
        _eff, meta = field_dict.resolve(fields, ctx)
        locked = [k for k, m in meta.items()
                  if m.get("locked") or not m.get("visible", True)]

    try:
        out = demand_agent.converse(
            history, text, material=material, locked_names=locked,
            facts=facts, filenames=[name for name, _path in paths],
            usage_ctx={"username": session.get("user", ""),
                       "display_name": me, "feature": "采购需求Agent对话"})
    except Exception as e:                                   # noqa: BLE001
        # Agent 挂了也要留一条，否则界面上是你说了话它没反应
        amsg = M(demand_id=did, demand_kind="gov", role="agent",
                 text=f"我这边出错了：{str(e)[:200]}。可以再说一遍，或者换份资料试试。",
                 created_by="agent", created_at=_now())
        db.session.add(amsg)
        db.session.commit()
        return jsonify({"ok": True, "data": {"user": umsg.to_dict(),
                                             "agent": amsg.to_dict()},
                        "facts": [f.to_dict() for f in _agent_facts(did)]})

    sug = None
    if out.get("fields") or out.get("packages") or out.get("questions"):
        sug = {"fields": out["fields"], "packages": out["packages"],
               "notes": out.get("notes") or [],
               "questions": out.get("questions") or []}
    amsg = M(demand_id=did, demand_kind="gov", role="agent",
             text=out.get("say") or "",
             suggestions_json=json.dumps(sug, ensure_ascii=False) if sug else "",
             created_by="agent", created_at=_now())
    db.session.add(amsg)
    db.session.flush()
    _save_agent_facts(did, out.get("facts"), umsg.id, me)
    db.session.commit()
    return jsonify({"ok": True, "data": {"user": umsg.to_dict(),
                                         "agent": amsg.to_dict()},
                    "facts": [f.to_dict() for f in _agent_facts(did)]})


@bp.route("/<int:did>/facts/<int:fid>", methods=["DELETE"])
@login_required
def demand_agent_fact_revoke(did, fid):
    """撤销一项事实并只重算必须重算的部分；历史消息保留。"""
    from models.demand_agent_fact import DemandAgentFact as F
    from models.demand_chat import DemandChatMessage as M
    from services import demand_agent, demand_agent_steps as steps
    _demand, _serr = _scoped(did)
    if _serr:
        return _serr
    fact = db.session.get(F, fid)
    if not fact or fact.demand_id != did or fact.demand_kind != "gov":
        return jsonify({"ok": False, "error": "这项确认不存在"}), 404
    revoked_key = fact.key
    db.session.delete(fact)
    db.session.flush()
    rows = db.session.execute(
        db.select(M).filter_by(demand_id=did, demand_kind="gov").order_by(M.id)
    ).scalars().all()

    def question(key, ask, why, kind="text", options=None, **extra):
        # 撤销后的问题仍走对话编排器的统一结构，
        # 否则前端的建议、置信度和选项标记会缺字段。
        return demand_agent._question(  # noqa: SLF001
            key, ask, why, kind, options, **extra)

    def fixed_question(key):
        """确定口径直接返回既有问题模板，不再请模型重新理解资料。"""
        if key.startswith("material_kind:"):
            filename = key.split(":", 1)[1] or "这份资料"
            return question(
                key, f"“{filename}”主要是什么资料？",
                "撤销原确认后要重新确定处理步骤，否则可能把内容填进错误位置",
                "choice", [
                    {"label": "技术参数", "value": "technical"},
                    {"label": "商务要求", "value": "business"},
                    {"label": "评审办法/分值", "value": "scoring"},
                    {"label": "项目基本信息", "value": "basic"},
                    {"label": "其他", "value": "other"},
                ])
        if key == "total_score":
            return question(
                key, "本项目技术分总分是多少？",
                "总分决定一般条款和▲条款各自分到多少分，不能沿用别的项目", "number",
                suggestion=50,
                suggestion_reason="这份资料原文没写技术分总分；同类项目常见按 50 分设置，"
                                  "这是经验值，不是从本文件读出的结论。按 50 分可继续分值计算；"
                                  "若项目采用其他总分，两类条款分值会随之变化。",
                confidence="medium")
        if key == "tri_ratio":
            return question(
                key, "▲条款与一般条款的分值怎么分配？请填写两类分值或▲占比。",
                "原文没有明确比例时套默认权重会造成评分办法错误", "text",
                suggestion=0.8,
                suggestion_reason="这份资料原文没写▲条款占比；同类项目常见让▲条款占技术分的 80%，"
                                  "这是经验值，不是原文结论。采用其他占比会直接改变一般条款和▲条款分值。",
                confidence="medium")
        if key == "count_rule":
            item = steps.calculate([], count_rule_confirmed=False)["uncertain"][0]
            item["suggestion"] = "leaf"
            item["suggestion_reason"] = (
                "这份资料原文没有检出完整计数规则；采购需求模板的通用口径是“无子项每条算 1 项、"
                "有子项按最末级子项算 1 项”。按此口径可以继续计算；若本项目文件另有原话，"
                "应改按原文复算。")
            item["confidence"] = "medium"
            item["options"][0]["suggested"] = True
            return item
        if key == "package_plan":
            return question(
                key, "这个项目分几个包，每个包对应资料的哪一段？",
                "分包边界决定技术、商务要求和预算分别写入哪个采购包", "text",
                suggestion_reason="现有资料没有同时读出明确包数、各包范围和金额，缺一项都可能串包，"
                                  "因此不提供建议。", confidence="low")
        if key == "price_deduct":
            return question(
                key, "价格扣除政策采用哪一项？",
                "小微企业、监狱企业、残疾人福利单位的适用口径要写入采购政策，不能代选", "choice", [
                    {"label": "小微企业", "value": "small_micro"},
                    {"label": "监狱企业", "value": "prison"},
                    {"label": "残疾人福利单位", "value": "disabled_welfare"},
                ], suggestion_reason="这是采购政策选择，不是从资料内容能判断的事实，硬给建议会误导，"
                                     "因此由经办人确认。", confidence="low")
        return question(
            key, f"请重新确认“{key}”。",
            "这项确认已撤销，后续计算不能继续使用旧值")

    def whole_question():
        """先复用已保存的分类产物；真没有时才重跑顶层条款分类。"""
        saved_question = None
        artifact_rows, whole = None, None
        for row in reversed(rows):
            suggestions = row.to_dict().get("suggestions") or {}
            for item in suggestions.get("questions") or []:
                if item.get("key") == "whole_tops" and saved_question is None:
                    saved_question = json.loads(json.dumps(item, ensure_ascii=False))
            for root_name in ("steps", "artifacts"):
                artifacts = suggestions.get(root_name) or {}
                technical = artifacts.get("technical") or {}
                for artifact in reversed(list(technical.values())):
                    if artifact.get("B_whole_tops"):
                        artifact_rows = artifact.get("A_clauses") or []
                        whole = artifact["B_whole_tops"]
                        break
                if whole:
                    break
            if whole:
                break
        if whole is None and saved_question is not None:
            # 旧消息可能是修复前生成的；撤销时顺手清掉
            # “13 条和 13 条”这种无差异对比，不需要因此再调模型。
            import re as _re
            reason = str(saved_question.get("suggestion_reason") or "")
            saved_question["suggestion_reason"] = _re.sub(
                r"▲条款分别是\s*(\d+)\s*条和\s*\1\s*条。", "", reason)
            return saved_question
        if whole is None:
            materials = []
            for row in rows:
                material = (getattr(row, "material", "") or "").strip()
                if material and material not in materials:
                    materials.append(material)
            artifact_rows = steps.parse_clauses("\n\n".join(materials[-8:]))
            whole = steps.classify_whole_tops(
                artifact_rows,
                usage_ctx={"username": session.get("user", ""),
                           "display_name": session.get("display_name", ""),
                           "feature": "采购需求Agent撤销事实-顶层条款复算"})

        pending = json.loads(json.dumps(whole.get("uncertain") or [], ensure_ascii=False))
        selected = whole.get("whole_tops") or []
        if not pending:
            pending = [question(
                "whole_tops", "这些带子项的顶层条款中，有没有配置清单、货物明细或附件列表？",
                "清单应整条计数，技术参数则按最末级子项计数，选错会改变条款总数")]
        if selected and artifact_rows:
            leaf_count = steps.calculate(artifact_rows, ())
            whole_count = steps.calculate(artifact_rows, selected)
            quotes = demand_agent._whole_top_quotes(artifact_rows, selected)  # noqa: SLF001
            reason = ""
            if quotes:
                reason = "原文可核对：" + "、".join(f"“{x}”" for x in quotes) + "。"
            model_reasons = [str((whole.get("reason") or {}).get(x) or "") for x in selected]
            if any(model_reasons):
                reason += "我的理解是" + "；".join(x for x in model_reasons if x) + "。"
            if whole_count["general"] != leaf_count["general"]:
                reason += (f"按配置清单整条计数，一般条款是 {whole_count['general']} 条；"
                           f"按子项逐条计数，一般条款会变成 {leaf_count['general']} 条。")
            if whole_count["tri"] != leaf_count["tri"]:
                reason += (f"按配置清单整条计数，▲条款是 {whole_count['tri']} 条；"
                           f"按子项逐条计数会变成 {leaf_count['tri']} 条。")
            level = demand_agent._confidence_label(whole.get("confidence"))  # noqa: SLF001
            for item in pending:
                item["confidence"] = level
                item["suggestion"] = "whole" if level != "low" else ""
                item["suggestion_reason"] = reason
                if item.get("options"):
                    item["options"][0]["suggested"] = level != "low"
        return pending[0]

    try:
        pending = whole_question() if revoked_key == "whole_tops" else fixed_question(revoked_key)
        label = {
            "whole_tops": "配置清单计数口径", "total_score": "技术分总分",
            "tri_ratio": "▲条款分值占比", "count_rule": "条款计数规则",
            "package_plan": "分包方案", "price_deduct": "价格扣除政策",
        }.get(revoked_key, "资料类型" if revoked_key.startswith("material_kind:") else revoked_key)
        sug = {"fields": {}, "packages": [], "notes": [], "questions": [pending]}
        amsg = M(demand_id=did, demand_kind="gov", role="agent",
                 text=f"已撤销『{label}』的确认，请重新确认下面的问题。",
                 suggestions_json=json.dumps(sug, ensure_ascii=False),
                 created_by="agent", created_at=_now())
        db.session.add(amsg)
        db.session.commit()
    except Exception as e:                                   # noqa: BLE001
        # 事实已经撤销就是成功；重算是后续动作，失败不能
        # 把整个撤销报成红叉，但要留下明确的下一步。
        label = {
            "whole_tops": "配置清单计数口径", "total_score": "技术分总分",
            "tri_ratio": "▲条款分值占比", "count_rule": "条款计数规则",
            "package_plan": "分包方案", "price_deduct": "价格扣除政策",
        }.get(revoked_key, "资料类型" if revoked_key.startswith("material_kind:") else revoked_key)
        amsg = M(demand_id=did, demand_kind="gov", role="agent",
                 text=f"已撤销『{label}』的确认。刚才重新核对时模型没响应，"
                      "你再发一句话或重新传一次资料，我就重算。",
                 created_by="agent", created_at=_now())
        db.session.add(amsg)
        db.session.commit()  # 同一次提交保存撤销结果和可操作的失败说明
        return jsonify({"ok": True, "data": {"agent": amsg.to_dict()},
                        "facts": [f.to_dict() for f in _agent_facts(did)]})
    return jsonify({"ok": True, "data": {"agent": amsg.to_dict()},
                    "facts": [f.to_dict() for f in _agent_facts(did)]})


@bp.route("/<int:did>/chat/<int:mid>/apply", methods=["POST"])
@login_required
def demand_chat_apply(did, mid):
    """采纳某条 Agent 消息里的建议（可只挑几项）。采纳结果回写到那条消息上。"""
    from models.demand_chat import DemandChatMessage as M
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    msg = db.session.get(M, mid)
    if not msg or msg.demand_id != did:
        return jsonify({"ok": False, "error": "这条消息不存在"}), 404

    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项的需求不可修改"}), 400
    body = request.get_json(silent=True) or {}
    out = _apply_agent_values(demand, body)
    # 采纳结果记在那条消息上，界面里能看出「这条我已经采纳过了」
    msg.applied_json = json.dumps(out.get("applied") or [], ensure_ascii=False)
    db.session.commit()
    return jsonify({"ok": True, **out})


@bp.route("/<int:did>/agent/suggest", methods=["POST"])
@login_required
def demand_agent_suggest(did):
    """读上传的资料（可多份），给出建议值。**不写库。**"""
    import tempfile
    from services import demand_agent, field_dict
    demand, _serr = _scoped(did)
    if _serr:
        return _serr

    files = [f for f in (request.files.getlist("file")
                         or request.files.getlist("files")) if f and f.filename]
    instruction = (request.form.get("instruction") or "").strip()
    pasted = (request.form.get("text") or "").strip()
    if not files and not pasted:
        return jsonify({"ok": False,
                        "error": "上传几份资料，或者把文字粘进来"}), 400

    tmpdir = tempfile.mkdtemp(prefix="agent_", dir=None)
    paths, rejected = [], []
    for f in files:
        name = os.path.basename(f.filename)
        ext = os.path.splitext(name)[1].lower()
        if ext not in AGENT_EXT:
            rejected.append(f"{name}（不支持 {ext or '无扩展名'}）")
            continue
        dst = os.path.join(tmpdir, name)
        f.save(dst)
        paths.append((name, dst))

    material, failed = demand_agent.read_files(paths)
    if pasted:
        material = (material + "\n\n【粘贴的文字】\n" + pasted).strip()
    if not material.strip():
        return jsonify({"ok": False,
                        "error": "这些资料里没读到文字。" +
                                 ("；".join(failed + rejected) or "")}), 400

    # 字典判定为锁定的字段，Agent 连建议都不给——那是规则定死的
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    from services import demand_doc
    ctx = demand_doc.build_context_for(demand, project)
    fields = field_dict.load(demand_doc.dict_name_for(demand))
    locked = []
    if fields:
        _eff, meta = field_dict.resolve(fields, ctx)
        locked = [k for k, m in meta.items() if m.get("locked") or not m.get("visible", True)]

    try:
        tri_ratio_raw = (request.form.get("tri_ratio") or "").strip()
        total_score_raw = (request.form.get("total_score") or "").strip()
        tri_ratio = float(tri_ratio_raw) if tri_ratio_raw else None
        total_score = float(total_score_raw) if total_score_raw else None
        if tri_ratio is not None and not 0 <= tri_ratio <= 1:
            raise ValueError("▲分值比例应在 0 到 1 之间")
        out = demand_agent.suggest(
            material, instruction, locked_names=locked,
            usage_ctx={"username": session.get("user", ""),
                       "display_name": session.get("display_name", ""),
                       "feature": "采购需求Agent填写"},
            total_score=total_score, tri_ratio=tri_ratio)
    except ValueError as e:
        return jsonify({"ok": False, "error": f"分值设置不正确：{e}"}), 400
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"ok": False, "error": f"Agent 没跑成：{e}"[:300]}), 500

    out["read"] = [n for n, _p in paths]
    out["failed"] = failed + rejected
    out["material_chars"] = len(material)
    return jsonify({"ok": True, "data": out})


@bp.route("/<int:did>/agent/steps/<action>", methods=["POST"])
@login_required
def demand_agent_step(did, action):
    """分步 Agent：A-F 每步均可独立查看、独立重跑，不直接写库。

    JSON 输入可带 text、rows、whole_tops、total_score、tri_ratio。action 支持
    clauses/whole-tops/count/technical-table/business/basic-info/all（也支持 A-F）。
    """
    from services import demand_agent_steps as steps
    _demand, _serr = _scoped(did)
    if _serr:
        return _serr
    body = request.get_json(silent=True) or {}
    text = str(body.get("text") or "")
    rows = body.get("rows")
    aliases = {
        "a": "clauses", "b": "whole-tops", "c": "count",
        "d": "technical-table", "e": "business", "f": "basic-info",
    }
    action = aliases.get(action.lower(), action.lower())
    usage_ctx = {"username": session.get("user", ""),
                 "display_name": session.get("display_name", ""),
                 "feature": f"采购需求Agent分步-{action}"}
    try:
        if action == "clauses":
            if not text.strip():
                return jsonify({"ok": False, "error": "请提供技术参数原文 text"}), 400
            artifact = steps.parse_clauses(text)
        elif action == "whole-tops":
            rows = rows or steps.parse_clauses(text)
            if not rows:
                return jsonify({"ok": False, "error": "请提供步骤 A 的 rows 或技术参数原文"}), 400
            artifact = steps.classify_whole_tops(rows, usage_ctx=usage_ctx)
        elif action == "count":
            rows = rows or steps.parse_clauses(text)
            if not rows:
                return jsonify({"ok": False, "error": "请提供步骤 A 的 rows 或技术参数原文"}), 400
            total_raw = body.get("total_score")
            total_score = float(total_raw) if total_raw not in (None, "") else None
            ratio = body.get("tri_ratio")
            ratio = float(ratio) if ratio is not None and ratio != "" else None
            explicit = steps.score_settings(text) if ratio is None and text else None
            if explicit:
                total_score, ratio = explicit["total_score"], explicit["tri_ratio"]
            if ratio is not None and not 0 <= ratio <= 1:
                raise ValueError("▲分值比例应在 0 到 1 之间")
            artifact = steps.calculate(rows, body.get("whole_tops") or (),
                                       total_score=total_score, tri_ratio=ratio)
        elif action == "technical-table":
            rows = rows or steps.parse_clauses(text)
            if not rows:
                return jsonify({"ok": False, "error": "请提供步骤 A 的 rows 或技术参数原文"}), 400
            artifact = steps.technical_table(rows)
        elif action == "business":
            if not text.strip():
                return jsonify({"ok": False, "error": "请提供商务相关原文 text"}), 400
            artifact = steps.business_requirements(text, usage_ctx=usage_ctx)
        elif action == "basic-info":
            if not text.strip():
                return jsonify({"ok": False, "error": "请提供相关信息原文 text"}), 400
            artifact = steps.basic_information(text, usage_ctx=usage_ctx)
        elif action == "all":
            if not text.strip():
                return jsonify({"ok": False, "error": "请提供资料原文 text"}), 400
            total_raw = body.get("total_score")
            total_score = float(total_raw) if total_raw not in (None, "") else None
            ratio = body.get("tri_ratio")
            ratio = float(ratio) if ratio is not None and ratio != "" else None
            if ratio is not None and not 0 <= ratio <= 1:
                raise ValueError("▲分值比例应在 0 到 1 之间")
            artifact = steps.run(text, total_score=total_score, tri_ratio=ratio,
                                 usage_ctx=usage_ctx)
        else:
            return jsonify({"ok": False, "error": "未知步骤；可用 A-F 或 all"}), 404
    except ValueError as e:
        return jsonify({"ok": False, "error": f"输入不正确：{e}"}), 400
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"ok": False, "error": f"步骤 {action} 没跑成：{e}"[:300]}), 500
    return jsonify({"ok": True, "step": action, "data": artifact})


def _apply_agent_values(demand, body):
    """把挑中的建议写进需求。抽出来给「一次性建议」和「对话」两处共用。

    返回 {"applied": [...], "skipped": [...], "message": ...}，不负责提交事务。
    """
    from services import demand_doc, field_dict
    picked = body.get("fields") or {}
    pkg_picked = body.get("packages") or []

    # 中文字段名 → 数据库列。只认这张表里的，别的一律不写。
    COL = {
        "项目概况": "project_overview",
        "相关产业发展情况": "survey_industry",
        "市场供给情况": "survey_market",
        "历史成交情况": "survey_history",
        "后续采购情况": "survey_followup",
        "其他相关情况": "survey_other",
        "合同履行期限": "contract_period",
        "合同履约地点": "contract_location",
        "合同支付约定": "payment_terms",
        "验收交付标准和方法": "acceptance_delivery",
        "质量保修范围和保修期": "warranty_terms",
        "履约验收程序": "acceptance_procedure",
        "履约验收时间": "acceptance_time",
    }

    # 再挡一道：字典锁定的字段，就算前端硬塞也不写
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    fields = field_dict.load(demand_doc.dict_name_for(demand))
    locked = set()
    if fields:
        ctx = demand_doc.build_context_for(demand, project)
        _eff, meta = field_dict.resolve(fields, ctx)
        locked = {k for k, m in meta.items()
                  if m.get("locked") or not m.get("visible", True)}

    applied, skipped = [], []
    for name, val in picked.items():
        if name in locked:
            skipped.append(f"{name}（字典锁定，不可由 Agent 改）")
            continue
        col = COL.get(name)
        if not col or not hasattr(demand, col):
            skipped.append(f"{name}（不在可写范围）")
            continue
        setattr(demand, col, str(val))
        applied.append(name)

    if pkg_picked:
        try:
            pkgs = json.loads(demand.packages_json or "[]") or [{}]
        except Exception:                                    # noqa: BLE001
            pkgs = [{}]
        while len(pkgs) < len(pkg_picked):
            pkgs.append({})
        for i, one in enumerate(pkg_picked):
            for k, v in (one or {}).items():
                if k in ("技术要求", "商务要求", "特殊资格要求"):
                    pkgs[i][k] = v
                    applied.append(f"包{i + 1}·{k}")
        demand.packages_json = json.dumps(pkgs, ensure_ascii=False)
        demand.package_count = len(pkgs)

    demand.updated_at = _now()
    msg = f"已采纳 {len(applied)} 项"
    if skipped:
        msg += f"；{len(skipped)} 项没写：" + "；".join(skipped[:3])
    return {"applied": applied, "skipped": skipped, "message": msg}


@bp.route("/<int:did>/agent/apply", methods=["POST"])
@login_required
def demand_agent_apply(did):
    """把人挑中的建议写进需求（一次性建议那条路）。"""
    demand, _serr = _scoped(did)
    if _serr:
        return _serr
    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项的需求不可修改"}), 400
    out = _apply_agent_values(demand, request.get_json(silent=True) or {})
    db.session.commit()
    return jsonify({"ok": True, **out})


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
