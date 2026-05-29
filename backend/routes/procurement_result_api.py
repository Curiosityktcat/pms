from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
import json
from models import db
from models.procurement_result import ProcurementResult
from models.project import Project
from routes.utils import login_required

bp = Blueprint("procurement_result", __name__, url_prefix="/api/procurement-results")


@bp.route("", methods=["GET"])
@login_required
def list_results():
    project_id = request.args.get("project_id", type=int)
    q = db.select(ProcurementResult)
    if project_id:
        q = q.where(ProcurementResult.project_id == project_id)
    rows = db.session.execute(q.order_by(ProcurementResult.id.desc())).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("", methods=["POST"])
@login_required
def create_result():
    data = request.get_json(force=True) or {}
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    packages = data.pop("packages", [])
    result = ProcurementResult(
        created_by=session.get("display_name", ""),
        created_at=now,
        updated_at=now,
        packages_json=json.dumps(packages, ensure_ascii=False),
        **{k: v for k, v in data.items()
           if hasattr(ProcurementResult, k)
           and k not in ("id", "created_at", "updated_at", "packages_json", "packages")}
    )
    db.session.add(result)
    db.session.commit()
    return jsonify({"ok": True, "data": result.to_dict()})


@bp.route("/<int:rid>", methods=["PUT"])
@login_required
def update_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data = request.get_json(force=True) or {}
    packages = data.pop("packages", None)
    if packages is not None:
        result.packages_json = json.dumps(packages, ensure_ascii=False)
    for k, v in data.items():
        if hasattr(result, k) and k not in ("id", "project_id", "created_by", "created_at", "packages_json", "packages"):
            setattr(result, k, v)
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "data": result.to_dict()})


@bp.route("/<int:rid>", methods=["DELETE"])
@login_required
def delete_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    db.session.delete(result)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<int:rid>/confirm", methods=["POST"])
@login_required
def confirm_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    result.status = "已确认"
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": "已确认"})


@bp.route("/<int:rid>/revoke", methods=["POST"])
@login_required
def revoke_result(rid):
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    result.status = "草稿"
    result.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回为草稿"})


@bp.route("/<int:rid>/word", methods=["GET"])
@login_required
def generate_word(rid):
    """生成采购结果确认函 Word 文档"""
    from services.procurement_result_word import generate
    result = db.session.get(ProcurementResult, rid)
    if not result:
        return jsonify({"ok": False, "error": "不存在"}), 404
    project = db.session.get(Project, result.project_id)
    try:
        buf, filename = generate(result, project)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500
