from flask import Blueprint, request, session, jsonify
from models import db
from models.project import Project
from models.agency import Agency
from services import project as svc
from services.numbering import M_YIJIA, M_XUNJIA, M_JINGXUAN, M_SOLE, M_JINGJI
from routes.utils import login_required

bp = Blueprint("project", __name__, url_prefix="/api/projects")

STATUSES = ["立项", "委托代理", "编制中", "审核中", "已发公告", "报名中", "开标", "已定标", "合同签订", "已归档"]


@bp.route("/meta", methods=["GET"])
@login_required
def meta():
    """前端立项表单需要的静态数据：代理机构列表、采购方式、状态列表。"""
    agencies = db.session.execute(db.select(Agency).filter_by(active=1)).scalars().all()
    return jsonify({
        "ok": True,
        "agencies": [a.to_dict() for a in agencies],
        "methods": [M_YIJIA, M_XUNJIA, M_JINGXUAN, M_SOLE, M_JINGJI],
        "statuses": STATUSES,
    })


@bp.route("", methods=["GET"])
@login_required
def list_projects():
    show_deleted = request.args.get("deleted") == "1"
    rows = svc.list_projects(
        role=session["role"],
        agency_code=session.get("agency_code", ""),
        officer=session.get("display_name", ""),
        show_deleted=show_deleted,
    )
    return jsonify({"ok": True, "data": rows, "total": len(rows)})


@bp.route("", methods=["POST"])
@login_required
def create_project():
    if session["role"] != "officer":
        return jsonify({"ok": False, "error": "仅项目经办人可立项"}), 403
    data = request.get_json(force=True) or {}
    try:
        p, number = svc.create_project(data, session["user"], session["display_name"])
        if p.is_draft:
            msg = "已存为草稿（未生成编号）"
        else:
            use_agency = bool(p.agency_code)
            msg = f"立项成功，编号 {number}（{'走代理' if use_agency else '不走代理'}，线{p.line}）"
        return jsonify({"ok": True, "message": msg, "data": p.to_dict()}), 201
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/<int:pid>", methods=["GET"])
@login_required
def get_project(pid):
    try:
        p = svc.get_project(
            pid,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
    except (ValueError, PermissionError) as e:
        code = 404 if isinstance(e, ValueError) else 403
        return jsonify({"ok": False, "error": str(e)}), code
    d = p.to_dict()
    d["agency_name"] = svc.get_agency_name(p.agency_code)
    agencies = db.session.execute(db.select(Agency).filter_by(active=1)).scalars().all()
    return jsonify({
        "ok": True,
        "data": d,
        "agencies": [a.to_dict() for a in agencies],
        "methods": [M_YIJIA, M_XUNJIA, M_JINGXUAN, M_SOLE, M_JINGJI],
        "statuses": STATUSES,
    })


@bp.route("/<int:pid>", methods=["PUT"])
@login_required
def update_project(pid):
    data = request.get_json(force=True) or {}
    try:
        p, number = svc.update_project(
            pid, data,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        msg = f"草稿已立项，编号 {number}" if number else "已保存"
        return jsonify({"ok": True, "message": msg, "data": p.to_dict()})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/<int:pid>", methods=["DELETE"])
@login_required
def delete_project(pid):
    try:
        svc.delete_project(
            pid,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        return jsonify({"ok": True, "message": "已删除（可在「已删除」标签中恢复）"})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 404


@bp.route("/<int:pid>/restore", methods=["POST"])
@login_required
def restore_project(pid):
    try:
        svc.restore_project(
            pid,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        return jsonify({"ok": True, "message": "项目已恢复"})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
