from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
import json, os
from models import db
from models.procurement_demand import ProcurementDemand
from models.project import Project
from models.agency import Agency
from routes.utils import login_required

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), '..', 'uploads', 'emergency')

bp = Blueprint("procurement_demand", __name__, url_prefix="/api/procurement-demands")

FLOW = ["草稿", "待分发", "已分发", "已立项"]


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

    q = db.select(ProcurementDemand).order_by(ProcurementDemand.id.desc())

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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 更新（仅草稿/已分发状态可编辑正文） ──────────────────────────
@bp.route("/<int:did>", methods=["PUT"])
@login_required
def update_demand(did):
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项的需求不可修改"}), 400

    data = request.get_json(force=True) or {}
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if demand.status != "草稿":
        return jsonify({"ok": False, "error": "只有草稿状态的需求可以删除"}), 400
    db.session.delete(demand)
    db.session.commit()
    return jsonify({"ok": True})


# ── 提交（草稿 → 待分发） ────────────────────────────────────────
@bp.route("/<int:did>/submit", methods=["POST"])
@login_required
def submit_demand(did):
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
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
    file  = request.files.get("file")
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if demand.status == "已立项":
        return jsonify({"ok": False, "error": "已立项，不可修改"}), 400
    file = request.files.get("file")
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
    demand = db.session.get(ProcurementDemand, did)
    if not demand or not demand.attachment_path:
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
