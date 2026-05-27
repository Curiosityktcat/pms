import datetime
from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.project import Project
from models.agency import Agency
from models.announcement import Announcement, QUAL_DEFAULTS
from services import announcement as svc
from routes.utils import login_required

bp = Blueprint("announcement", __name__, url_prefix="/api/announcements")

ANN_TYPES = ["procurement", "survey", "correction", "single_source"]
ANN_TYPE_CN = {
    "procurement": "采购公告",
    "survey": "调研公告",
    "correction": "更正公告",
    "single_source": "单一来源公示",
}


def _get_agency_name(agency_code):
    if not agency_code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=agency_code)).scalar_one_or_none()
    return a.name if a else agency_code


def _enrich(ann):
    d = ann.to_dict()
    project = db.session.get(Project, ann.project_id)
    if project:
        d["project_name"] = project.name
        d["project_number"] = project.number
        d["agency_name"] = _get_agency_name(project.agency_code)
        d["project_agency_code"] = project.agency_code or ""
    else:
        d["project_name"] = ""
        d["project_number"] = ""
        d["agency_name"] = ""
        d["project_agency_code"] = ""
    d["ann_type_cn"] = ANN_TYPE_CN.get(ann.ann_type, ann.ann_type)
    return d


def _can_edit(ann_or_project_agency_code: str) -> bool:
    """当前用户是否有权编辑该公告（经办人/助理/负责人全权；代理只能编辑自己的）"""
    role = session.get("role", "")
    if role in ("officer", "assistant", "leader"):
        return True
    if role == "agency":
        return session.get("agency_code", "") == ann_or_project_agency_code
    return False


def _can_confirm() -> bool:
    """只有经办人/助理/负责人可以确认公告"""
    return session.get("role", "") in ("officer", "assistant", "leader")


def _apply_fields(ann: Announcement, data: dict):
    """把 POST/PUT 的字段写入 ann 对象（共用逻辑）"""
    ann.ann_type = data.get("ann_type", ann.ann_type)
    ann.round_number = int(data.get("round_number", ann.round_number) or 1)
    ann.project_intro = (data.get("project_intro") or "").strip()
    ann.special_req = (data.get("special_req") or "").strip()
    # 一般资格要求
    ann.qual_1 = (data.get("qual_1") or QUAL_DEFAULTS[0]).strip()
    ann.qual_2 = (data.get("qual_2") or QUAL_DEFAULTS[1]).strip()
    ann.qual_3 = (data.get("qual_3") or QUAL_DEFAULTS[2]).strip()
    ann.qual_4 = (data.get("qual_4") or QUAL_DEFAULTS[3]).strip()
    ann.qual_5 = (data.get("qual_5") or QUAL_DEFAULTS[4]).strip()
    ann.qual_6 = (data.get("qual_6") or QUAL_DEFAULTS[5]).strip()
    # 时间
    ann.reg_start = (data.get("reg_start") or "").strip()
    ann.reg_end = (data.get("reg_end") or "").strip()
    ann.reg_note = (data.get("reg_note") or "").strip()
    ann.response_deadline = (data.get("response_deadline") or "").strip()
    # 代理信息
    ann.agency_address = (data.get("agency_address") or "").strip()
    ann.delivery_address = (data.get("delivery_address") or "").strip()
    ann.agency_email = (data.get("agency_email") or "").strip()
    ann.agency_reg_phone = (data.get("agency_reg_phone") or "").strip()
    ann.agency_contact = (data.get("agency_contact") or "").strip()
    ann.agency_contact_phone = (data.get("agency_contact_phone") or "").strip()


# ── 列表 ──────────────────────────────────────────────────────────
@bp.route("", methods=["GET"])
@login_required
def list_announcements():
    ann_type = request.args.get("type", "procurement")
    stmt = (
        db.select(Announcement)
        .where(Announcement.ann_type == ann_type)
        .order_by(Announcement.id.desc())
    )
    rows = db.session.execute(stmt).scalars().all()

    role = session.get("role", "")
    my_agency = session.get("agency_code", "")

    result = []
    for a in rows:
        d = _enrich(a)
        # 代理机构只看自己的
        if role == "agency" and d.get("project_agency_code") != my_agency:
            continue
        result.append(d)
    return jsonify({"ok": True, "data": result})


# ── 创建 ──────────────────────────────────────────────────────────
@bp.route("", methods=["POST"])
@login_required
def create_announcement():
    data = request.get_json(force=True) or {}
    pid = data.get("project_id")
    if not pid:
        return jsonify({"ok": False, "error": "请选择项目"}), 400

    project = db.session.get(Project, int(pid))
    if not project or project.is_draft:
        return jsonify({"ok": False, "error": "项目不存在或尚未正式立项"}), 400
    if not project.agency_code:
        return jsonify({"ok": False, "error": "该项目未走代理机构，无法生成采购公告"}), 400

    if not _can_edit(project.agency_code):
        return jsonify({"ok": False, "error": "权限不足，只能编制本机构负责的项目公告"}), 403

    now = datetime.datetime.now().isoformat(timespec="seconds")
    ann = Announcement(
        project_id=int(pid),
        status="草稿",
        created_at=now,
        created_by=session.get("display_name", ""),
    )
    _apply_fields(ann, data)
    db.session.add(ann)
    db.session.commit()
    return jsonify({"ok": True, "message": "已保存草稿", "data": _enrich(ann)}), 201


# ── 获取单条 ──────────────────────────────────────────────────────
@bp.route("/<int:aid>", methods=["GET"])
@login_required
def get_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    d = _enrich(ann)
    # 代理机构权限检查
    if session.get("role") == "agency" and d.get("project_agency_code") != session.get("agency_code", ""):
        return jsonify({"ok": False, "error": "无权查看"}), 403
    return jsonify({"ok": True, "data": d})


# ── 更新 ──────────────────────────────────────────────────────────
@bp.route("/<int:aid>", methods=["PUT"])
@login_required
def update_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404

    project = db.session.get(Project, ann.project_id)
    agency_code = project.agency_code if project else ""

    if not _can_edit(agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403

    # 已确认的公告只有经办人/负责人可以再编辑
    if ann.status == "已确认" and not _can_confirm():
        return jsonify({"ok": False, "error": "公告已确认，如需修改请联系经办人"}), 403

    data = request.get_json(force=True) or {}
    _apply_fields(ann, data)
    # 代理修改后如果状态是"待确认"，改回"草稿"（需重新提交）
    if ann.status == "待确认" and session.get("role") == "agency":
        ann.status = "草稿"
    db.session.commit()
    return jsonify({"ok": True, "message": "已保存", "data": _enrich(ann)})


# ── 删除 ──────────────────────────────────────────────────────────
@bp.route("/<int:aid>", methods=["DELETE"])
@login_required
def delete_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404

    project = db.session.get(Project, ann.project_id)
    agency_code = project.agency_code if project else ""

    if not _can_edit(agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认" and not _can_confirm():
        return jsonify({"ok": False, "error": "已确认的公告无法删除，请联系经办人"}), 403

    db.session.delete(ann)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ── 提交确认（代理→待确认）────────────────────────────────────────
@bp.route("/<int:aid>/submit", methods=["POST"])
@login_required
def submit_announcement(aid):
    """代理机构提交公告，状态改为待确认，等待经办人确认"""
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404

    project = db.session.get(Project, ann.project_id)
    agency_code = project.agency_code if project else ""

    if not _can_edit(agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认":
        return jsonify({"ok": False, "error": "公告已经确认，无需重复提交"}), 400

    ann.status = "待确认"
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交，等待经办人确认", "data": _enrich(ann)})


# ── 确认（经办人→已确认）──────────────────────────────────────────
@bp.route("/<int:aid>/confirm", methods=["POST"])
@login_required
def confirm_announcement(aid):
    """经办人/负责人确认公告"""
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可确认公告"}), 403

    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    if ann.status == "已确认":
        return jsonify({"ok": False, "error": "公告已经确认"}), 400

    now = datetime.datetime.now().isoformat(timespec="seconds")
    ann.status = "已确认"
    ann.confirmed_by = session.get("display_name", "")
    ann.confirmed_at = now
    db.session.commit()
    return jsonify({"ok": True, "message": "公告已确认", "data": _enrich(ann)})


# ── 撤回确认（恢复草稿）──────────────────────────────────────────
@bp.route("/<int:aid>/revoke", methods=["POST"])
@login_required
def revoke_announcement(aid):
    """撤回确认，恢复为草稿（仅经办人/负责人）"""
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可撤回确认"}), 403

    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404

    ann.status = "草稿"
    ann.confirmed_by = ""
    ann.confirmed_at = ""
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回确认，恢复为草稿", "data": _enrich(ann)})


# ── 生成 Word ─────────────────────────────────────────────────────
@bp.route("/<int:aid>/generate", methods=["POST"])
@login_required
def generate_word(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404

    project = db.session.get(Project, ann.project_id)
    if not project:
        return jsonify({"ok": False, "error": "关联项目不存在"}), 400
    if not project.agency_code:
        return jsonify({"ok": False, "error": "项目未关联代理机构"}), 400

    agency_name = _get_agency_name(project.agency_code)
    try:
        buf = svc.generate(project, ann, agency_name)
        filename = svc.get_filename(project, ann)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500


# ── 项目列表（供前端选择） ──────────────────────────────────────
@bp.route("/projects", methods=["GET"])
@login_required
def eligible_projects():
    """返回可生成采购公告的项目：已正式立项 + 走代理机构"""
    role = session.get("role", "")
    my_agency = session.get("agency_code", "")

    stmt = (
        db.select(Project)
        .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
        .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
        .where(Project.agency_code != "")
        .order_by(Project.id.desc())
    )
    rows = db.session.execute(stmt).scalars().all()

    result = []
    for p in rows:
        # 代理机构只看自己的项目
        if role == "agency" and p.agency_code != my_agency:
            continue
        result.append({
            "id": p.id,
            "name": p.name,
            "number": p.number,
            "agency_code": p.agency_code,
            "agency_name": _get_agency_name(p.agency_code),
            "status": p.status,
        })
    return jsonify({"ok": True, "data": result})
