"""系统管理员维护科室字典。"""
import re

from flask import Blueprint, jsonify, request

from models import db
from models.dept import Dept, _split
from models.user import User
from routes.utils import admin_required

bp = Blueprint("dept_admin", __name__, url_prefix="/api/admin/depts")
CATEGORIES = {"归口", "需求", "实施", "职能", "监督", "法务"}


def _error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def _values(data, current=None):
    code = (data.get("code", getattr(current, "code", "")) or "").strip().upper()
    name = (data.get("name", getattr(current, "name", "")) or "").strip()
    aliases_raw = data.get("aliases", getattr(current, "aliases", ""))
    aliases = ",".join(_split(",".join(aliases_raw) if isinstance(aliases_raw, list) else aliases_raw))
    category_raw = data.get("category", getattr(current, "category", ""))
    categories = _split(",".join(category_raw) if isinstance(category_raw, list) else category_raw)
    if not code or not re.fullmatch(r"[A-Z]+", code):
        return None, "科室编码只能使用大写字母"
    if not name:
        return None, "科室名称不能为空"
    if any(category not in CATEGORIES for category in categories):
        return None, "科室分类不正确"
    dept_type = (data.get("dept_type", getattr(current, "dept_type", "")) or "").strip()
    if dept_type not in ("", "行后", "临床医技"):
        return None, "科室类型只能是行后或临床医技"
    try:
        sort_no = int(data.get("sort_no", getattr(current, "sort_no", 0)) or 0)
    except (TypeError, ValueError):
        return None, "排序号必须是整数"
    return {"code": code, "name": name, "aliases": aliases,
            "category": ",".join(categories),
            "active": 1 if data.get("active", getattr(current, "active", 1)) in (1, True, "1") else 0,
            "sort_no": sort_no, "dept_type": dept_type,
            "head_name": (data.get("head_name", getattr(current, "head_name", "")) or "").strip(),
            "note": (data.get("note", getattr(current, "note", "")) or "").strip()}, ""


@bp.route("", methods=["GET"])
@admin_required
def list_depts():
    rows = db.session.execute(db.select(Dept).order_by(Dept.sort_no, Dept.id)).scalars().all()
    return jsonify({"ok": True, "data": [row.to_dict() for row in rows]})


@bp.route("", methods=["POST"])
@admin_required
def create_dept():
    values, error = _values(request.get_json(force=True) or {})
    if error:
        return _error(error)
    if db.session.execute(db.select(Dept.id).filter_by(code=values["code"])).scalar_one_or_none() is not None:
        return _error("科室编码已存在")
    dept = Dept(**values)
    db.session.add(dept)
    db.session.commit()
    return jsonify({"ok": True, "data": dept.to_dict()}), 201


@bp.route("/<int:dept_id>", methods=["PUT"])
@admin_required
def update_dept(dept_id):
    dept = db.session.get(Dept, dept_id)
    if not dept:
        return _error("科室不存在", 404)
    values, error = _values(request.get_json(force=True) or {}, dept)
    if error:
        return _error(error)
    duplicate = db.session.execute(
        db.select(Dept.id).where(Dept.code == values["code"], Dept.id != dept.id)
    ).scalar_one_or_none()
    if duplicate is not None:
        return _error("科室编码已存在")
    # 编码被账号引用时不可改，否则账号会悄悄失去科室归属。
    bound = db.session.execute(db.select(db.func.count()).select_from(User).filter_by(dept_code=dept.code)).scalar_one()
    if bound and values["code"] != dept.code:
        return _error("已有账号绑定该科室，不能修改科室编码")
    for key, value in values.items():
        setattr(dept, key, value)
    db.session.commit()
    return jsonify({"ok": True, "data": dept.to_dict()})


@bp.route("/<int:dept_id>", methods=["DELETE"])
@admin_required
def delete_dept(dept_id):
    dept = db.session.get(Dept, dept_id)
    if not dept:
        return _error("科室不存在", 404)
    bound = db.session.execute(db.select(db.func.count()).select_from(User).filter_by(dept_code=dept.code)).scalar_one()
    if bound:
        return _error(f"已有 {bound} 个账号绑定该科室，只能停用，不能删除")
    db.session.delete(dept)
    db.session.commit()
    return jsonify({"ok": True})
