"""代理机构信息维护：列表/新增/编辑/停用。

机构基本信息（法人、联系方式、地址等）由采购部助理手工维护，
供代理协议、合同等模块自动填充。删除采用「停用」(active=0)，避免影响历史项目引用。
"""
from flask import Blueprint, request, jsonify, session

from models import db
from models.agency import Agency
from routes.utils import login_required
from services.permission import is_admin_user

bp = Blueprint("agency", __name__, url_prefix="/api/agencies")

_MANAGE_ROLES = ("assistant", "pd_assistant", "leader")


def _can_manage():
    return session.get("role") in _MANAGE_ROLES or is_admin_user(session.get("user", ""))


_FIELDS = ("code", "name", "legal_rep", "phone", "address",
           "in_rotation", "rotation_seq", "is_central", "active")


def _apply(a, data):
    for f in _FIELDS:
        if f in data:
            v = data[f]
            if f in ("in_rotation", "rotation_seq", "is_central", "active"):
                v = int(v or 0)
            else:
                v = (v or "").strip()
            setattr(a, f, v)


@bp.route("", methods=["GET"])
@login_required
def list_agencies():
    """全部机构（含停用），轮派在前、集采在后；前端可自行过滤。"""
    rows = db.session.execute(
        db.select(Agency).order_by(Agency.is_central.asc(), Agency.rotation_seq.asc(), Agency.id.asc())
    ).scalars().all()
    return jsonify({"ok": True, "data": [a.to_dict() for a in rows]})


@bp.route("", methods=["POST"])
@login_required
def create_agency():
    if not _can_manage():
        return jsonify({"ok": False, "error": "无权限"}), 403
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    name = (data.get("name") or "").strip()
    if not code or not name:
        return jsonify({"ok": False, "error": "机构代码和名称必填"}), 400
    if db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none():
        return jsonify({"ok": False, "error": f"机构代码 {code} 已存在"}), 400
    a = Agency(code=code, name=name, active=1)
    _apply(a, data)
    db.session.add(a)
    db.session.commit()
    return jsonify({"ok": True, "data": a.to_dict()})


@bp.route("/<int:aid>", methods=["PUT"])
@login_required
def update_agency(aid):
    if not _can_manage():
        return jsonify({"ok": False, "error": "无权限"}), 403
    a = db.session.get(Agency, aid)
    if not a:
        return jsonify({"ok": False, "error": "机构不存在"}), 404
    data = request.get_json(silent=True) or {}
    new_code = (data.get("code") or a.code).strip()
    if new_code != a.code and db.session.execute(
            db.select(Agency).filter_by(code=new_code)).scalar_one_or_none():
        return jsonify({"ok": False, "error": f"机构代码 {new_code} 已存在"}), 400
    _apply(a, data)
    db.session.commit()
    return jsonify({"ok": True, "data": a.to_dict()})


@bp.route("/<int:aid>", methods=["DELETE"])
@login_required
def deactivate_agency(aid):
    """停用（不物理删除，避免影响历史项目的 agency_code 引用）。"""
    if not _can_manage():
        return jsonify({"ok": False, "error": "无权限"}), 403
    a = db.session.get(Agency, aid)
    if not a:
        return jsonify({"ok": False, "error": "机构不存在"}), 404
    a.active = 0
    db.session.commit()
    return jsonify({"ok": True})
