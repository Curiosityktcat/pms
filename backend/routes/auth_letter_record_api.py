import datetime
from flask import Blueprint, request, session, jsonify
from models import db
from models.auth_letter_record import AuthLetterRecord
from models.project import Project
from routes.utils import login_required

bp = Blueprint("auth_letter_record", __name__, url_prefix="/api/auth-letter-records")


@bp.route("", methods=["GET"])
@login_required
def list_records():
    """列出所有授权函记录（已授权）"""
    role = session.get("role", "")
    officer = session.get("display_name", "")
    agency_code = session.get("agency_code", "")

    query = db.select(AuthLetterRecord).order_by(AuthLetterRecord.id.desc())
    rows = db.session.execute(query).scalars().all()

    result = []
    for r in rows:
        # 按角色过滤
        if role == "officer":
            p = db.session.get(Project, r.project_id)
            if p and p.officer != officer:
                continue
        elif role == "agency":
            p = db.session.get(Project, r.project_id)
            if p and p.agency_code != agency_code:
                continue
        result.append(r.to_dict())

    return jsonify({"ok": True, "data": result})


@bp.route("", methods=["POST"])
@login_required
def create_record():
    """生成授权函 Word 后，保存一条记录"""
    data = request.get_json(force=True) or {}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    record = AuthLetterRecord(
        project_id=int(data.get("project_id", 0)),
        project_name=data.get("project_name", ""),
        project_number=data.get("project_number", ""),
        round_number=int(data.get("round_number", 1)),
        bid_time=data.get("bid_time", ""),
        supervisor_name=data.get("supervisor_name", ""),
        representative_names=data.get("representative_names", ""),
        generated_by=session.get("display_name", ""),
        generated_at=now,
    )
    db.session.add(record)
    db.session.commit()
    return jsonify({"ok": True, "message": "已保存授权函记录", "data": record.to_dict()}), 201


@bp.route("/<int:rid>", methods=["DELETE"])
@login_required
def delete_record(rid):
    """删除授权函记录（仅经办人/领导）"""
    role = session.get("role", "")
    if role not in ("officer", "assistant", "leader"):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    r = db.session.get(AuthLetterRecord, rid)
    if not r:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    db.session.delete(r)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})
