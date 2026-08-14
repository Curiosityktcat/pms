import datetime
import os
from flask import (
    Blueprint, request, session, jsonify, send_file, after_this_request,
)
from models import db
from models.auth_letter_record import AuthLetterRecord
from models.project import Project
from routes.utils import login_required

bp = Blueprint("auth_letter_record", __name__, url_prefix="/api/auth-letter-records")


def _can_view_project(project):
    """当前登录身份是否有权查看该项目的授权函记录。"""
    role = session.get("role", "")
    if role == "officer":
        return not project or project.officer == session.get("display_name", "")
    if role == "agency":
        return not project or project.agency_code == session.get("agency_code", "")
    return True


@bp.route("", methods=["GET"])
@login_required
def list_records():
    """列出所有授权函记录（已授权）"""
    query = db.select(AuthLetterRecord).order_by(AuthLetterRecord.id.desc())
    rows = db.session.execute(query).scalars().all()

    result = []
    for r in rows:
        p = db.session.get(Project, r.project_id)
        if not _can_view_project(p):
            continue
        result.append(r.to_dict())

    return jsonify({"ok": True, "data": result})


@bp.route("/<int:rid>/word", methods=["GET"])
@login_required
def download_record_word(rid):
    """按已保存的授权函记录重新生成 Word 并下载。

    代理机构需要看到/打印授权函内容，但记录只存了人员姓名（未存文件），
    故按姓名反查人员（含身份证号与照片）后用同一模板重出。
    """
    from models.people import People
    from models.agency import Agency
    from services import auth_letter as svc

    rec = db.session.get(AuthLetterRecord, rid)
    if not rec:
        return jsonify({"ok": False, "error": "记录不存在"}), 404

    project = db.session.get(Project, rec.project_id)
    if not _can_view_project(project):
        return jsonify({"ok": False, "error": "无权查看该授权函"}), 403
    if not project:
        return jsonify({"ok": False, "error": "对应项目已不存在，无法重新生成"}), 404

    def _find_person(name):
        name = (name or "").strip()
        if not name:
            return None
        return db.session.execute(
            db.select(People).filter_by(name=name)
        ).scalars().first()

    supervisor = _find_person(rec.supervisor_name)
    if not supervisor:
        return jsonify({
            "ok": False,
            "error": f"未在人员库中找到监督人员「{rec.supervisor_name}」，请到人员管理核对后重新生成",
        }), 400

    rep_names = [n for n in (rec.representative_names or "").split("、") if n.strip()]
    representatives = []
    missing = []
    for n in rep_names:
        person = _find_person(n)
        if person:
            representatives.append(person)
        else:
            missing.append(n)
    if missing:
        return jsonify({
            "ok": False,
            "error": "未在人员库中找到采购人代表：" + "、".join(missing) + "，请到人员管理核对后重新生成",
        }), 400
    if not representatives:
        return jsonify({"ok": False, "error": "该记录无采购人代表，无法生成"}), 400

    agency_name = ""
    if project.agency_code:
        a = db.session.execute(
            db.select(Agency).filter_by(code=project.agency_code)
        ).scalar_one_or_none()
        agency_name = a.name if a else project.agency_code

    try:
        tmp_path = svc.generate(
            project, supervisor, representatives, agency_name,
            round_number=rec.round_number or 1,
            bid_time_override=rec.bid_time or "",
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    suffix = svc.get_round_suffix(rec.round_number or 1)
    download_name = f"授权函_{project.number or project.name}{suffix}.docx"

    @after_this_request
    def cleanup(response):
        try:
            os.remove(tmp_path)
        except Exception:
            pass
        return response

    return send_file(
        tmp_path,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=download_name,
    )


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
    # 授权函生成 → 自动推到 rd-web 采购项目审批盖章（同轮已成功推过的不重复推）
    from routes.rdweb_approval_api import auto_push_on_confirm
    from models.project import Project as _Prj
    _p = db.session.get(_Prj, record.project_id)
    push_info = auto_push_on_confirm(_p, "auth_letter", record.round_number or 1) if _p else {}
    return jsonify({"ok": True, "message": "已保存授权函记录",
                    "data": record.to_dict(), "rdweb_push": push_info}), 201


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
