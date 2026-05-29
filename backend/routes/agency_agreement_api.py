from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.project import Project
from models.agency import Agency
from routes.utils import login_required

bp = Blueprint("agency_agreement", __name__, url_prefix="/api/projects")


@bp.route("/<int:pid>/agency-agreement", methods=["POST"])
@login_required
def generate_agency_agreement(pid):
    """按模板生成委托代理协议 Word（仅走代理项目）。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if project.is_draft:
        return jsonify({"ok": False, "error": "草稿项目无法生成代理协议"}), 400
    if not project.agency_code:
        return jsonify({"ok": False, "error": "该项目不走代理机构，无需生成代理协议"}), 400

    # 权限：经办人仅限本人项目，代理机构仅限本机构项目
    role = session.get("role", "")
    if role == "officer" and project.officer != session.get("display_name", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403

    data = request.get_json(silent=True) or {}

    # 代理机构全称
    a = db.session.execute(
        db.select(Agency).filter_by(code=project.agency_code)
    ).scalar_one_or_none()
    agency_name = (data.get("agency_name") or (a.name if a else project.agency_code)).strip()

    from services.agency_agreement_word import generate
    try:
        buf, filename = generate(
            project, agency_name,
            agency_address=(data.get("agency_address") or "").strip(),
            officer_name=(data.get("officer_name") or "").strip(),
            officer_phone=(data.get("officer_phone") or "0832-2256120").strip(),
            sign_date=(data.get("sign_date") or "").strip(),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )
