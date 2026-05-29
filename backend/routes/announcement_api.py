import datetime
import html as html_module
import io
import os
import uuid
from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.project import Project
from models.agency import Agency
from models.announcement import Announcement, QUALIFICATIONS_DEFAULT
from models.announcement_attachment import AnnouncementAttachment
from services import announcement as svc
from routes.utils import login_required

bp = Blueprint("announcement", __name__, url_prefix="/api/announcements")

# 附件存储根目录
UPLOAD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "announcements")
)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

ANN_TYPE_CN = {
    "procurement": "采购公告",
    "survey": "调研公告",
    "correction": "更正公告",
    "single_source": "单一来源公示",
}

ALLOWED_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".zip", ".rar",
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


def _can_edit(project_agency_code: str) -> bool:
    role = session.get("role", "")
    if role in ("officer", "assistant", "leader"):
        return True
    if role == "agency":
        return session.get("agency_code", "") == project_agency_code
    return False


def _can_confirm() -> bool:
    return session.get("role", "") in ("officer", "assistant", "leader")


def _apply_fields(ann: Announcement, data: dict):
    ann.ann_type = data.get("ann_type", ann.ann_type)
    ann.round_number = int(data.get("round_number", ann.round_number) or 1)
    ann.project_intro = (data.get("project_intro") or "").strip()
    ann.qualifications = (data.get("qualifications") or QUALIFICATIONS_DEFAULT).strip()
    ann.special_req = (data.get("special_req") or "").strip()
    ann.reg_start = (data.get("reg_start") or "").strip()
    ann.reg_end = (data.get("reg_end") or "").strip()
    ann.reg_note = (data.get("reg_note") or "").strip()
    ann.response_deadline = (data.get("response_deadline") or "").strip()
    ann.agency_address = (data.get("agency_address") or "").strip()
    ann.delivery_address = (data.get("delivery_address") or "").strip()
    ann.agency_email = (data.get("agency_email") or "").strip()
    ann.agency_reg_phone = (data.get("agency_reg_phone") or "").strip()
    ann.agency_contact = (data.get("agency_contact") or "").strip()
    ann.agency_contact_phone = (data.get("agency_contact_phone") or "").strip()


# ── 公开列表（无需登录，供登录页展示） ───────────────────────────────
@bp.route("/public", methods=["GET"])
def public_announcements():
    """无需登录：返回所有已确认（已挂网）的公告，供登录页面公开展示"""
    ann_type = request.args.get("type", "procurement")
    rows = db.session.execute(
        db.select(Announcement)
        .where(Announcement.ann_type == ann_type)
        .where(Announcement.status == "已确认")
        .order_by(Announcement.id.desc())
        .limit(50)
    ).scalars().all()
    return jsonify({"ok": True, "data": [_enrich(a) for a in rows]})


# ── 公开单条详情（无需登录） ──────────────────────────────────────────
@bp.route("/public/<int:aid>", methods=["GET"])
def public_announcement_detail(aid):
    """无需登录：返回单条已发布公告的完整内容"""
    ann = db.session.get(Announcement, aid)
    if not ann or ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告不存在或尚未发布"}), 404
    return jsonify({"ok": True, "data": _enrich(ann)})


# ── 公开附件列表（无需登录） ──────────────────────────────────────────
@bp.route("/public/<int:aid>/files", methods=["GET"])
def public_list_files(aid):
    """无需登录：返回已发布公告的附件列表"""
    ann = db.session.get(Announcement, aid)
    if not ann or ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告不存在或尚未发布"}), 404
    rows = db.session.execute(
        db.select(AnnouncementAttachment)
        .where(AnnouncementAttachment.announcement_id == aid)
        .order_by(AnnouncementAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


# ── 公开附件下载（无需登录） ──────────────────────────────────────────
@bp.route("/public/<int:aid>/files/<int:fid>", methods=["GET"])
def public_download_file(aid, fid):
    """无需登录：下载已发布公告的附件"""
    ann = db.session.get(Announcement, aid)
    if not ann or ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告不存在或尚未发布"}), 404
    att = db.session.get(AnnouncementAttachment, fid)
    if not att or att.announcement_id != aid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_file_dir(aid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请联系管理员"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


# ── 公开 Word 下载（无需登录，实时生成） ──────────────────────────────
@bp.route("/public/<int:aid>/word", methods=["GET"])
def public_generate_word(aid):
    """无需登录：为已发布公告实时生成并下载 Word 文档"""
    ann = db.session.get(Announcement, aid)
    if not ann or ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告不存在或尚未发布"}), 404
    project = db.session.get(Project, ann.project_id)
    if not project:
        return jsonify({"ok": False, "error": "关联项目不存在"}), 400

    agency_name = _get_agency_name(project.agency_code) if project.agency_code else ""
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


# ── 公开 HTML 渲染（无需登录，用 python-docx 精准提取格式） ──────────
@bp.route("/public/<int:aid>/html", methods=["GET"])
def public_announcement_html(aid):
    """无需登录：把已发布公告的 Word 转成保留格式的 HTML 片段返回"""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    ann = db.session.get(Announcement, aid)
    if not ann or ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告不存在或尚未发布"}), 404
    project = db.session.get(Project, ann.project_id)
    if not project:
        return jsonify({"ok": False, "error": "关联项目不存在"}), 400

    agency_name = _get_agency_name(project.agency_code) if project.agency_code else ""
    try:
        buf = svc.generate(project, ann, agency_name)
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500

    doc = Document(buf)
    parts = []

    for para in doc.paragraphs:
        raw = para.text
        # 跳过完全空行，但保留只有空格的行（避免丢失间距）
        if not raw.strip():
            parts.append('<p style="margin:0;line-height:1.5em;">&nbsp;</p>')
            continue

        # 对齐方式
        align = para.alignment
        if align == WD_ALIGN_PARAGRAPH.CENTER:
            align_style = "text-align:center;"
        elif align == WD_ALIGN_PARAGRAPH.RIGHT:
            align_style = "text-align:right;"
        elif align == WD_ALIGN_PARAGRAPH.JUSTIFY:
            align_style = "text-align:justify;"
        else:
            align_style = "text-align:left;"

        # 首行缩进：304800 EMU ≈ 2字符（模板标准值）
        first_indent = para.paragraph_format.first_line_indent
        indent_style = ""
        if first_indent and first_indent > 100000 and align != WD_ALIGN_PARAGRAPH.CENTER:
            indent_style = "text-indent:2em;"

        style = f"margin:4px 0;line-height:1.8;font-size:16px;{align_style}{indent_style}"

        # 逐 run 拼 span
        inner = ""
        for run in para.runs:
            if not run.text:
                continue
            t = html_module.escape(run.text)
            run_styles = []
            if run.bold:
                run_styles.append("font-weight:bold")
            if run.underline:
                run_styles.append("text-decoration:underline")
            if run.font.size:
                pt = run.font.size.pt
                run_styles.append(f"font-size:{pt}pt")
            if run_styles:
                inner += f'<span style="{";".join(run_styles)}">{t}</span>'
            else:
                inner += t

        parts.append(f'<p style="{style}">{inner}</p>')

    return jsonify({"ok": True, "html": "\n".join(parts)})


# ── 列表 ──────────────────────────────────────────────────────────
@bp.route("", methods=["GET"])
@login_required
def list_announcements():
    ann_type = request.args.get("type", "procurement")
    rows = db.session.execute(
        db.select(Announcement)
        .where(Announcement.ann_type == ann_type)
        .order_by(Announcement.id.desc())
    ).scalars().all()

    role = session.get("role", "")
    my_agency = session.get("agency_code", "")
    result = []
    for a in rows:
        d = _enrich(a)
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
        qualifications=QUALIFICATIONS_DEFAULT,
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
    if ann.status == "已确认" and not _can_confirm():
        return jsonify({"ok": False, "error": "公告已确认，如需修改请联系经办人"}), 403

    data = request.get_json(force=True) or {}
    _apply_fields(ann, data)
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

    # 同时删除附件文件
    attachments = db.session.execute(
        db.select(AnnouncementAttachment).where(AnnouncementAttachment.announcement_id == aid)
    ).scalars().all()
    for att in attachments:
        _delete_file(att)
        db.session.delete(att)

    db.session.delete(ann)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ── 提交确认 ──────────────────────────────────────────────────────
@bp.route("/<int:aid>/submit", methods=["POST"])
@login_required
def submit_announcement(aid):
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


# ── 确认/发布 ─────────────────────────────────────────────────────
@bp.route("/<int:aid>/confirm", methods=["POST"])
@login_required
def confirm_announcement(aid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可确认发布"}), 403
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    if ann.status == "已确认":
        return jsonify({"ok": False, "error": "公告已经发布"}), 400
    now = datetime.datetime.now().isoformat(timespec="seconds")
    ann.status = "已确认"
    ann.confirmed_by = session.get("display_name", "")
    ann.confirmed_at = now

    # ── 自动将响应截止时间（开标时间）同步到项目 ────────────────────
    if ann.response_deadline:
        project = db.session.get(Project, ann.project_id)
        if project and not project.bid_time:
            # 只在项目尚无开标时间时才自动填入，避免覆盖手动设置
            project.bid_time = ann.response_deadline

    db.session.commit()
    return jsonify({"ok": True, "message": "公告已发布，开标时间已同步至项目", "data": _enrich(ann)})


# ── 撤回确认 ──────────────────────────────────────────────────────
@bp.route("/<int:aid>/revoke", methods=["POST"])
@login_required
def revoke_announcement(aid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可撤回确认"}), 403
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    ann.status = "草稿"
    ann.confirmed_by = ""
    ann.confirmed_at = ""
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回，恢复为草稿", "data": _enrich(ann)})


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


# ──────────────────────────────────────────────────────────────────
# 附件接口
# ──────────────────────────────────────────────────────────────────

def _file_dir(announcement_id: int) -> str:
    d = os.path.join(UPLOAD_ROOT, str(announcement_id))
    os.makedirs(d, exist_ok=True)
    return d


def _delete_file(att: AnnouncementAttachment):
    try:
        path = os.path.join(_file_dir(att.announcement_id), att.saved_name)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# 上传附件
@bp.route("/<int:aid>/files", methods=["POST"])
@login_required
def upload_file(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    agency_code = project.agency_code if project else ""
    if not _can_edit(agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认" and not _can_confirm():
        return jsonify({"ok": False, "error": "公告已确认，无法上传附件"}), 403

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400

    # 检查扩展名
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False, "error": f"不支持的文件格式：{ext}，支持 PDF/Word/Excel/图片/压缩包"}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(_file_dir(aid), saved_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)

    now = datetime.datetime.now().isoformat(timespec="seconds")
    att = AnnouncementAttachment(
        announcement_id=aid,
        original_name=f.filename,
        saved_name=saved_name,
        file_size=file_size,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=now,
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "上传成功", "data": att.to_dict()}), 201


# 列出附件
@bp.route("/<int:aid>/files", methods=["GET"])
@login_required
def list_files(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    rows = db.session.execute(
        db.select(AnnouncementAttachment)
        .where(AnnouncementAttachment.announcement_id == aid)
        .order_by(AnnouncementAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


# 下载附件
@bp.route("/<int:aid>/files/<int:fid>", methods=["GET"])
@login_required
def download_file(aid, fid):
    att = db.session.get(AnnouncementAttachment, fid)
    if not att or att.announcement_id != aid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_file_dir(aid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


# 删除附件
@bp.route("/<int:aid>/files/<int:fid>", methods=["DELETE"])
@login_required
def delete_file(aid, fid):
    att = db.session.get(AnnouncementAttachment, fid)
    if not att or att.announcement_id != aid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    ann = db.session.get(Announcement, aid)
    project = db.session.get(Project, ann.project_id) if ann else None
    agency_code = project.agency_code if project else ""
    if not _can_edit(agency_code):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    _delete_file(att)
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ── 项目列表（供前端选择） ──────────────────────────────────────
@bp.route("/projects", methods=["GET"])
@login_required
def eligible_projects():
    role = session.get("role", "")
    my_agency = session.get("agency_code", "")
    rows = db.session.execute(
        db.select(Project)
        .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
        .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
        .where(Project.agency_code != "")
        .order_by(Project.id.desc())
    ).scalars().all()
    result = []
    for p in rows:
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
