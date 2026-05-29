"""项目归档：汇总项目要件并归档/撤销归档。"""
import datetime
from flask import Blueprint, session, jsonify
from models import db
from models.project import Project
from models.auth_letter_record import AuthLetterRecord
from models.contract import Contract
from models.procurement_result import ProcurementResult
from routes.utils import login_required

bp = Blueprint("archive", __name__, url_prefix="/api/archive")

ARCHIVED = "已归档"
# 撤销归档后回退到的状态
REVOKE_STATUS = "合同签订"


def _count(model, pid):
    return db.session.execute(
        db.select(db.func.count()).select_from(model).filter_by(project_id=pid)
    ).scalar_one()


@bp.route("", methods=["GET"])
@login_required
def list_archive():
    """列出可归档/已归档项目及其要件统计。"""
    role = session.get("role", "")
    officer = session.get("display_name", "")
    agency_code = session.get("agency_code", "")

    rows = db.session.execute(
        db.select(Project)
        .filter(Project.is_draft == 0, Project.is_deleted == 0)
        .order_by(Project.id.desc())
    ).scalars().all()

    result = []
    for p in rows:
        if role == "officer" and p.officer != officer:
            continue
        if role == "agency" and p.agency_code != agency_code:
            continue
        result.append({
            "id": p.id,
            "number": p.number or "",
            "name": p.name or "",
            "officer": p.officer or "",
            "agency_code": p.agency_code or "",
            "status": p.status or "",
            "archived": p.status == ARCHIVED,
            "auth_letter_count": _count(AuthLetterRecord, p.id),
            "contract_count": _count(Contract, p.id),
            "result_count": _count(ProcurementResult, p.id),
        })
    return jsonify({"ok": True, "data": result})


def _can_archive():
    role = session.get("role", "")
    from services.permission import is_admin_user
    return role in ("assistant", "leader") or is_admin_user(session.get("user", ""))


@bp.route("/<int:pid>", methods=["POST"])
@login_required
def archive_project(pid):
    """归档项目（仅助理/负责人/管理员）。"""
    if not _can_archive():
        return jsonify({"ok": False, "error": "仅采购部助理/负责人可归档"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if p.is_draft:
        return jsonify({"ok": False, "error": "草稿项目不可归档"}), 400
    p.status = ARCHIVED
    p.updated_at = datetime.datetime.now().isoformat(timespec="seconds")
    db.session.commit()
    return jsonify({"ok": True, "message": "已归档", "status": p.status})


@bp.route("/<int:pid>/revoke", methods=["POST"])
@login_required
def revoke_archive(pid):
    """撤销归档，状态回退到「合同签订」。"""
    if not _can_archive():
        return jsonify({"ok": False, "error": "仅采购部助理/负责人可操作"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if p.status != ARCHIVED:
        return jsonify({"ok": False, "error": "该项目未归档"}), 400
    p.status = REVOKE_STATUS
    p.updated_at = datetime.datetime.now().isoformat(timespec="seconds")
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤销归档", "status": p.status})
