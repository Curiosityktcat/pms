import datetime
from flask import Blueprint, request, session, jsonify
from models import db
from models.agency_template import AgencyTemplate
from routes.utils import login_required

bp = Blueprint("agency_template", __name__, url_prefix="/api/agency-templates")


def _my_agency():
    return session.get("agency_code", "")


def _can_manage(agency_code: str) -> bool:
    """代理机构只能管理自己的模板；经办人/助理/负责人可管理所有"""
    role = session.get("role", "")
    if role in ("officer", "assistant", "leader"):
        return True
    if role == "agency":
        return _my_agency() == agency_code
    return False


# ── 列表 ──────────────────────────────────────────────────────────
@bp.route("", methods=["GET"])
@login_required
def list_templates():
    """列出当前用户可见的模板（代理只看自己的，经办人可按 agency_code 筛选）"""
    role = session.get("role", "")
    if role == "agency":
        agency_code = _my_agency()
    else:
        # 支持按 agency_code 参数过滤
        agency_code = request.args.get("agency_code", "")

    stmt = db.select(AgencyTemplate).order_by(AgencyTemplate.id.desc())
    if agency_code:
        stmt = stmt.where(AgencyTemplate.agency_code == agency_code)
    rows = db.session.execute(stmt).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


# ── 创建 ──────────────────────────────────────────────────────────
@bp.route("", methods=["POST"])
@login_required
def create_template():
    data = request.get_json(force=True) or {}
    agency_code = (data.get("agency_code") or _my_agency()).strip()
    if not agency_code:
        return jsonify({"ok": False, "error": "请指定代理机构"}), 400
    if not _can_manage(agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    template_name = (data.get("template_name") or "").strip()
    if not template_name:
        return jsonify({"ok": False, "error": "请填写模板名称"}), 400

    now = datetime.datetime.now().isoformat(timespec="seconds")
    tpl = AgencyTemplate(
        agency_code=agency_code,
        template_name=template_name,
        agency_address=(data.get("agency_address") or "").strip(),
        delivery_address=(data.get("delivery_address") or "").strip(),
        agency_email=(data.get("agency_email") or "").strip(),
        agency_reg_phone=(data.get("agency_reg_phone") or "").strip(),
        agency_contact=(data.get("agency_contact") or "").strip(),
        agency_contact_phone=(data.get("agency_contact_phone") or "").strip(),
        created_at=now,
        updated_at=now,
    )
    db.session.add(tpl)
    db.session.commit()
    return jsonify({"ok": True, "message": "模板已创建", "data": tpl.to_dict()}), 201


# ── 更新 ──────────────────────────────────────────────────────────
@bp.route("/<int:tid>", methods=["PUT"])
@login_required
def update_template(tid):
    tpl = db.session.get(AgencyTemplate, tid)
    if not tpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not _can_manage(tpl.agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403

    data = request.get_json(force=True) or {}
    tpl.template_name = (data.get("template_name") or tpl.template_name).strip()
    tpl.agency_address = (data.get("agency_address") or "").strip()
    tpl.delivery_address = (data.get("delivery_address") or "").strip()
    tpl.agency_email = (data.get("agency_email") or "").strip()
    tpl.agency_reg_phone = (data.get("agency_reg_phone") or "").strip()
    tpl.agency_contact = (data.get("agency_contact") or "").strip()
    tpl.agency_contact_phone = (data.get("agency_contact_phone") or "").strip()
    tpl.updated_at = datetime.datetime.now().isoformat(timespec="seconds")
    db.session.commit()
    return jsonify({"ok": True, "message": "模板已更新", "data": tpl.to_dict()})


# ── 删除 ──────────────────────────────────────────────────────────
@bp.route("/<int:tid>", methods=["DELETE"])
@login_required
def delete_template(tid):
    tpl = db.session.get(AgencyTemplate, tid)
    if not tpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not _can_manage(tpl.agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    db.session.delete(tpl)
    db.session.commit()
    return jsonify({"ok": True, "message": "模板已删除"})
