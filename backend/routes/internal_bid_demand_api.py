from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
import json
from models import db
from models.internal_bid_demand import InternalBidDemand
from models.project import Project
from routes.utils import login_required
from services.permission import is_admin_user
from services.dept_scope import assert_can_write_demand, assert_has_writable_perm, is_dept_role, scope_by_project

bp = Blueprint("internal_bid_demand", __name__, url_prefix="/api/internal-bid-demands")


def _now():
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _scope_ok(demand) -> bool:
    """院内招标需求归属：本人起草(created_by) 或关联项目归本人经办；
    助理/负责人/管理员全部；代理机构不可见（院内文件）。"""
    role = session.get("role", "")
    if role in ("assistant", "leader") or is_admin_user(session.get("user", "")):
        return True
    if role == "agency":
        return False
    me = session.get("display_name", "")
    if (demand.created_by or "") == me:
        return True
    if demand.project_id:
        p = db.session.get(Project, demand.project_id)
        return bool(p) and (p.officer or "") == me
    return False


def _scoped(did):
    demand = db.session.get(InternalBidDemand, did)
    if not demand:
        return None, (jsonify({"ok": False, "error": "不存在"}), 404)
    if is_dept_role():
        assert_has_writable_perm("internal-bid-demand")
        assert_can_write_demand(demand.demand_dept, demand.project_id)
        return demand, None
    if not _scope_ok(demand):
        return None, (jsonify({"ok": False, "error": "无权访问该院内招标需求"}), 403)
    return demand, None


def _enrich(d: InternalBidDemand):
    data = d.to_dict()  # 已含手填的 project_name / budget_amount
    p = db.session.get(Project, d.project_id) if d.project_id else None
    # 手填优先；为空再回落到（历史遗留的）关联项目
    if not data.get("project_name"):
        data["project_name"] = p.name if p else ""
    if not data.get("budget_amount"):
        data["budget_amount"] = (p.amount if p else 0) or 0
    data["project_number"] = p.number if p else ""
    return data


# ── 列表 ─────────────────────────────────────────────────────
@bp.route("", methods=["GET"])
@login_required
def list_demands():
    project_id = request.args.get("project_id", type=int)
    status_filter = request.args.get("status", "")

    q = scope_by_project(
        db.select(InternalBidDemand), InternalBidDemand
    ).order_by(InternalBidDemand.id.desc())
    if project_id:
        q = q.where(InternalBidDemand.project_id == project_id)
    if status_filter:
        q = q.where(InternalBidDemand.status == status_filter)

    rows = db.session.execute(q).scalars().all()
    if not is_dept_role():
        rows = [r for r in rows if _scope_ok(r)]   # 既有角色仍按本人起草/本人项目隔离
    return jsonify({"ok": True, "data": [_enrich(r) for r in rows]})


# ── 创建 ─────────────────────────────────────────────────────
@bp.route("", methods=["POST"])
@login_required
def create_demand():
    data = request.get_json(force=True) or {}
    assert_has_writable_perm("internal-bid-demand")
    assert_can_write_demand(data.get("demand_dept"))
    now = _now()

    allowed = {c.name for c in InternalBidDemand.__table__.columns}
    locked = {"id", "created_at", "updated_at", "status"}
    filtered = {k: v for k, v in data.items() if k in allowed and k not in locked}

    demand = InternalBidDemand(
        status="初稿",
        created_by=session.get("display_name", ""),
        created_at=now,
        updated_at=now,
        **filtered,
    )
    db.session.add(demand)
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 获取单条 ─────────────────────────────────────────────────
@bp.route("/<int:did>", methods=["GET"])
@login_required
def get_demand(did):
    demand, err = _scoped(did)
    if err:
        return err
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 更新 ─────────────────────────────────────────────────────
@bp.route("/<int:did>", methods=["PUT"])
@login_required
def update_demand(did):
    demand, err = _scoped(did)
    if err:
        return err
    if demand.status == "定稿":
        return jsonify({"ok": False, "error": "定稿状态不可修改，请先撤回"}), 400

    data = request.get_json(force=True) or {}
    if "demand_dept" in data:
        assert_can_write_demand(data.get("demand_dept"))
    locked = {"id", "created_by", "created_at", "status"}
    for k, v in data.items():
        if hasattr(demand, k) and k not in locked:
            setattr(demand, k, v)
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich(demand)})


# ── 删除（仅初稿） ───────────────────────────────────────────
@bp.route("/<int:did>", methods=["DELETE"])
@login_required
def delete_demand(did):
    demand, err = _scoped(did)
    if err:
        return err
    if demand.status != "初稿":
        return jsonify({"ok": False, "error": "只有初稿状态可以删除"}), 400
    db.session.delete(demand)
    db.session.commit()
    return jsonify({"ok": True})


# ── 定稿（初稿 → 定稿） ──────────────────────────────────────
@bp.route("/<int:did>/finalize", methods=["POST"])
@login_required
def finalize_demand(did):
    demand, err = _scoped(did)
    if err:
        return err
    if demand.status != "初稿":
        return jsonify({"ok": False, "error": "只有初稿状态可以定稿"}), 400
    demand.status = "定稿"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已定稿"})


# ── 撤回（定稿 → 初稿） ──────────────────────────────────────
@bp.route("/<int:did>/revoke", methods=["POST"])
@login_required
def revoke_demand(did):
    demand, err = _scoped(did)
    if err:
        return err
    if demand.status != "定稿":
        return jsonify({"ok": False, "error": "只有定稿状态可以撤回"}), 400
    demand.status = "初稿"
    demand.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回为初稿"})


# ── 生成 Word ─────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════
# 按模板出稿：和政府采购需求共用同一份《2.2 采购需求表》模板
# （自行采购只是「标绿部分无需填写」，表是同一张）。
# 字段名对不上、是否题存成 0/1，映射在 services/demand_doc.build_context_internal。
# ══════════════════════════════════════════════════════════════════

@bp.route("/<int:did>/doc-status", methods=["GET"])
@login_required
def internal_doc_status(did):
    from services import demand_doc
    import os as _os
    demand, err = _scoped(did)
    if err:
        return err
    if not _os.path.exists(demand_doc.TEMPLATE):
        return jsonify({"ok": False, "error": "还没配采购需求表模板"}), 404
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    ctx = demand_doc.build_context_for(demand, project)
    missing = demand_doc.missing_fields(ctx)
    total = len(demand_doc.load_fields())
    return jsonify({"ok": True, "data": {
        "total": total, "filled": total - len(missing),
        "missing": [{"name": m["name"], "label": m["label"], "kind": m["kind"]}
                    for m in missing],
    }})


@bp.route("/<int:did>/doc", methods=["GET"])
@login_required
def internal_doc_file(did):
    """?download=1 下载 Word，否则转 PDF 给右边的预览用（iframe 渲染不了 docx）。"""
    from services import demand_doc
    demand, err = _scoped(did)
    if err:
        return err
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    try:
        buf, _missing = demand_doc.render(demand, project)
    except FileNotFoundError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"ok": False, "error": f"套打失败：{e}"[:300]}), 500

    name = (demand.project_name or f"院内竞选需求{did}").strip()[:60]
    if request.args.get("download") == "1":
        return send_file(
            buf, as_attachment=True, download_name=f"{name}-采购需求表.docx",
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    import os as _os
    import tempfile
    tmpdir = tempfile.mkdtemp(prefix="internaldoc_")
    src = _os.path.join(tmpdir, f"{name}.docx")
    with open(src, "wb") as fh:
        fh.write(buf.getvalue())
    from services.office_convert import to_pdf
    try:
        pdf = to_pdf(src)
    except Exception as e:                                   # noqa: BLE001
        return jsonify({"ok": False,
                        "error": f"转 PDF 失败，预览用不了（可以先下载 Word 看）：{e}"[:300]}), 500
    return send_file(pdf, mimetype="application/pdf", as_attachment=False,
                     download_name=f"{name}-采购需求表.pdf")


@bp.route("/<int:did>/word", methods=["GET"])
@login_required
def generate_word(did):
    from services.internal_bid_demand_word import generate
    demand, err = _scoped(did)
    if err:
        return err
    project = db.session.get(Project, demand.project_id) if demand.project_id else None
    try:
        buf, filename = generate(demand, project)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500
