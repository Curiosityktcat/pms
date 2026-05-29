from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.project import Project
from models.agency import Agency
from routes.utils import login_required

bp = Blueprint("procurement_doc", __name__, url_prefix="/api/projects")


def _check_project_access(project):
    """返回 (ok, error_json, status)；校验项目可用且当前用户有权操作。"""
    if not project:
        return False, {"ok": False, "error": "项目不存在"}, 404
    if project.is_draft:
        return False, {"ok": False, "error": "草稿项目无法生成采购文件"}, 400
    if not project.agency_code:
        return False, {"ok": False, "error": "该项目不走代理机构"}, 400
    role = session.get("role", "")
    if role == "officer" and project.officer != session.get("display_name", ""):
        return False, {"ok": False, "error": "无权操作该项目"}, 403
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return False, {"ok": False, "error": "无权操作该项目"}, 403
    return True, None, 200


def _agency_name(project, override=""):
    if override:
        return override.strip()
    a = db.session.execute(
        db.select(Agency).filter_by(code=project.agency_code)
    ).scalar_one_or_none()
    return a.name if a else project.agency_code


@bp.route("/<int:pid>/bid-cover", methods=["POST"])
@login_required
def generate_bid_cover(pid):
    """按模板生成招标文件封面 Word。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    from services.bid_cover_word import generate
    try:
        buf, filename = generate(
            project,
            _agency_name(project, data.get("agency_name", "")),
            compile_date=(data.get("compile_date") or "").strip(),
            round_number=int(data.get("round_number") or project.round or 1),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )
