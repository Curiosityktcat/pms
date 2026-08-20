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
from services import approval_log as alog
from services.permission import is_admin_user
from services.dept_scope import scope_by_project, scope_projects, visible_project_ids
from routes.utils import login_required
from services import upload_relay

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

# 可以编制采购公告的采购方式。单一来源保留在内是为了兼容历史数据（早期
# 有项目挂过采购公告），但它不再进「待编公告」待办——单一来源不挂网，
# 直接邀请供应商谈判，它需要的是「单一来源公示」(ann_type='single_source')。
ANNOUNCEMENT_METHODS = ("院内竞选", "院内单一来源采购")
# 真正会被系统催着挂采购公告的方式
ANNOUNCEMENT_REQUIRED_METHODS = ("院内竞选",)

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


def _node_of(ann) -> str:
    """公告类型 → 审批日志节点键（更正公告单独成节点，便于归档分开列）。"""
    return "correction" if ann.ann_type == "correction" else "announcement"


def _scope_ok(project) -> bool:
    """当前用户是否有权访问该项目的公告。与项目列表口径一致：
    agency 只看本机构、officer 只看本人经办、assistant/leader/admin 全部。"""
    if not project:
        return False
    role = session.get("role", "")
    if role in ("dept", "dept_manage", "dept_demand"):
        return project.id in (visible_project_ids() or set())
    if role == "agency":
        return (project.agency_code or "") == session.get("agency_code", "")
    if role == "officer":
        return (project.officer or "") == session.get("display_name", "")
    return role in ("assistant", "leader") or is_admin_user(session.get("user", ""))


def _can_edit(project) -> bool:
    """可编辑公告内容：采购人方（officer 限本人 / assistant / leader）或本机构代理。"""
    if not _scope_ok(project):
        return False
    role = session.get("role", "")
    return role in ("officer", "assistant", "leader", "agency")


def _can_confirm(project) -> bool:
    """确认/撤回公告仅限采购人方（officer 限本人经办 / assistant / leader）。"""
    if not _scope_ok(project):
        return False
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
    # 更正公告专用字段（其他类型公告传了也无害）
    ann.corr_scope = (data.get("corr_scope") or ann.corr_scope or "").strip()
    ann.corr_reason = (data.get("corr_reason") or "").strip()
    if "corr_items_json" in data:
        ann.corr_items_json = data.get("corr_items_json") or "[]"
    if "corr_in_attachment" in data:
        ann.corr_in_attachment = 1 if data.get("corr_in_attachment") else 0
    # 调研公告（6.2）与单一来源公示（6.4）专用字段
    for f in ("survey_content", "survey_qualification", "survey_quote_req",
              "survey_materials", "survey_deadline", "survey_submit_way",
              "survey_note", "ss_goods_desc", "ss_reason", "ss_supplier_name",
              "ss_supplier_addr", "ss_publicity_start", "ss_publicity_end",
              "ss_objection_dept", "ss_objection_contact", "ss_objection_phone",
              "ss_objection_addr"):
        if f in data:
            v = (data.get(f) or "").strip()
            # 前端把非法日期 format() 出来会是字面量 "Invalid Date"，
            # 存进去用户就会看到「公示期 Invalid Date 至 Invalid Date」。
            # 这类值一律当空处理，不让脏数据落库。
            if f.startswith("ss_publicity") and "Invalid" in v:
                v = ""
            setattr(ann, f, v)
    if "ss_experts_json" in data:
        ann.ss_experts_json = data.get("ss_experts_json") or "[]"


def _sync_project_round(project):
    """项目的「第X次」后缀由该项目采购公告的最大开标次数自动带动。

    立项阶段不存在「第几次采购」——它等于第几次开标：第一次挂公告开标废标后
    才执行第二次。因此项目层面的 round 不再手填，而是跟随采购公告的 round_number。
    """
    if not project:
        return
    max_round = db.session.execute(
        db.select(db.func.max(Announcement.round_number))
        .where(Announcement.project_id == project.id)
        .where(Announcement.ann_type == "procurement")
    ).scalar()
    project.round = max_round or 1


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
def _generic_html(ann, project, agency_name):
    """调研/更正/单一来源公告无独立 Word 模板，按存储字段生成通用 HTML。"""
    esc = html_module.escape
    type_cn = ANN_TYPE_CN.get(ann.ann_type, "公告")
    parts = [
        f'<p style="text-align:center;font-size:20px;font-weight:bold;margin:8px 0;">'
        f'{esc(project.name or "")}{esc(type_cn)}</p>'
    ]
    # 正文（project_intro 作为公告正文，按换行分段，首行缩进）
    body = (ann.project_intro or "").strip()
    if body:
        for line in body.split("\n"):
            line = line.strip()
            if not line:
                parts.append('<p style="margin:0;line-height:1.8;">&nbsp;</p>')
            else:
                parts.append(
                    f'<p style="margin:4px 0;line-height:1.8;font-size:16px;'
                    f'text-indent:2em;text-align:justify;">{esc(line)}</p>'
                )
    rows = []
    if ann.response_deadline:
        rows.append(("响应/反馈截止时间", ann.response_deadline))
    if ann.reg_note:
        rows.append(("备注", ann.reg_note))
    if agency_name:
        rows.append(("采购代理机构", agency_name))
    if ann.agency_contact or ann.agency_contact_phone:
        rows.append(("联系人", f"{ann.agency_contact} {ann.agency_contact_phone}".strip()))
    if ann.agency_address:
        rows.append(("地址", ann.agency_address))
    for label, val in rows:
        parts.append(
            f'<p style="margin:4px 0;line-height:1.8;font-size:16px;">'
            f'<b>{esc(label)}：</b>{esc(str(val))}</p>'
        )
    return "\n".join(parts)


def _generate_word_buf(project, ann, agency_name):
    """按公告类型分发 Word 生成器，返回 (BytesIO, filename)。"""
    if ann.ann_type == "correction":
        from services import correction_word as corr_svc
        return corr_svc.generate(project, ann, agency_name), corr_svc.get_filename(project, ann)
    if ann.ann_type == "survey":
        from services.survey_ss_word import build_survey
        return build_survey(ann, project)
    if ann.ann_type == "single_source":
        from services.survey_ss_word import build_single_source
        return build_single_source(ann, project)
    return svc.generate(project, ann, agency_name), svc.get_filename(project, ann)


@bp.route("/public/<int:aid>/word", methods=["GET"])
def public_generate_word(aid):
    """无需登录：为已发布公告实时生成并下载 Word 文档"""
    ann = db.session.get(Announcement, aid)
    if not ann or ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告不存在或尚未发布"}), 404
    if ann.ann_type not in ("procurement", "correction"):
        return jsonify({"ok": False, "error": "该类公告暂未提供 Word 模板，请在系统内查看或打印"}), 400
    project = db.session.get(Project, ann.project_id)
    if not project:
        return jsonify({"ok": False, "error": "关联项目不存在"}), 400

    agency_name = _get_agency_name(project.agency_code) if project.agency_code else ""
    try:
        buf, filename = _generate_word_buf(project, ann, agency_name)
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
        buf, _ = _generate_word_buf(project, ann, agency_name)
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
        scope_by_project(db.select(Announcement), Announcement)
        .where(Announcement.ann_type == ann_type)
        .order_by(Announcement.id.desc())
    ).scalars().all()

    # 隔离：agency 只看本机构、officer 只看本人经办、assistant/leader/admin 全部
    result = []
    for a in rows:
        project = db.session.get(Project, a.project_id)
        if not _scope_ok(project):
            continue
        result.append(_enrich(a))
    from services.pending_owner import attach_pending
    attach_pending(result, "project_id")      # 每行带上当前处理人
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
    if not _can_edit(project):
        return jsonify({"ok": False, "error": "权限不足，只能编制本机构负责的项目公告"}), 403
    # 采购公告仅限院内竞选/单一来源项目，且须在采购文件经办人确认后方可编制
    if data.get("ann_type", "procurement") == "procurement":
        if project.method not in ANNOUNCEMENT_METHODS:
            return jsonify({"ok": False, "error": "仅院内竞选/单一来源采购项目需要编制采购公告"}), 400
        if not project.doc_confirmed:
            return jsonify({"ok": False, "error": "采购文件尚未经办人确认，无法编制采购公告"}), 400
        # 每轮只能发一次：本轮已存在采购公告则拒绝重复创建
        target_round = int(data.get("round_number") or project.round or 1)
        dup = db.session.execute(
            db.select(Announcement.id).where(
                Announcement.project_id == project.id,
                Announcement.ann_type == "procurement",
                Announcement.round_number == target_round,
            )
        ).first()
        if dup:
            return jsonify({"ok": False, "error": f"该项目第 {target_round} 次采购公告已存在，每轮只能发布一次"}), 400

    corr_seq = 1
    # 更正公告：须在「本轮采购公告已发布、开标结果未判定」窗口内（公告后、开标前）
    if data.get("ann_type") == "correction":
        target_round = int(data.get("round_number") or project.round or 1)
        src = db.session.execute(
            db.select(Announcement).where(
                Announcement.project_id == project.id,
                Announcement.ann_type == "procurement",
                Announcement.round_number == target_round,
                Announcement.status == "已确认",
            )
        ).scalars().first()
        if not src:
            return jsonify({"ok": False, "error": f"该项目第 {target_round} 次采购公告尚未发布，无法发布更正公告"}), 400
        from models.procurement_round import ProcurementRound
        rnd = db.session.execute(
            db.select(ProcurementRound).filter_by(
                project_id=project.id, round_number=target_round)
        ).scalar_one_or_none()
        # 仅「开标前」可更正：与开标管理 active 口径一致——「可开标」确认可发生在开标时间之前，
        # 此时仍是开标前、可更正；只有「流标已确认」或「开标时间已过」才算开标后、不可更正。
        if rnd and rnd.can_open_status == "已确认":
            from services.bid import _parse_cn_deadline
            from datetime import datetime as _dtc
            if rnd.can_open != "可开标":
                return jsonify({"ok": False, "error": "本轮已流标，更正公告须在开标前发布"}), 400
            _ddl = _parse_cn_deadline(src.response_deadline or project.bid_time or "")
            if _ddl is None or _dtc.now().date() > _ddl.date():
                return jsonify({"ok": False, "error": "本轮已开标（开标时间已过），更正公告须在开标前发布"}), 400
        # 第几次更正 = 本项目本轮已有更正公告数 + 1
        corr_seq = (db.session.execute(
            db.select(db.func.count()).select_from(Announcement).where(
                Announcement.project_id == project.id,
                Announcement.ann_type == "correction",
                Announcement.round_number == target_round,
            )
        ).scalar_one() or 0) + 1

    now = datetime.datetime.now().isoformat(timespec="seconds")
    ann = Announcement(
        project_id=int(pid),
        qualifications=QUALIFICATIONS_DEFAULT,
        status="草稿",
        created_at=now,
        created_by=session.get("display_name", ""),
    )
    _apply_fields(ann, data)
    if ann.ann_type == "correction":
        ann.corr_seq = corr_seq
        # 联系信息默认承接原采购公告（可再编辑）
        if data.get("ann_type") == "correction" and not ann.agency_contact:
            src_ann = db.session.execute(
                db.select(Announcement).where(
                    Announcement.project_id == project.id,
                    Announcement.ann_type == "procurement",
                    Announcement.round_number == ann.round_number,
                    Announcement.status == "已确认",
                )
            ).scalars().first()
            if src_ann:
                ann.agency_address = src_ann.agency_address
                ann.agency_email = src_ann.agency_email
                ann.agency_contact = src_ann.agency_contact
                ann.agency_contact_phone = src_ann.agency_contact_phone
    db.session.add(ann)
    _sync_project_round(project)
    db.session.commit()
    return jsonify({"ok": True, "message": "已保存草稿", "data": _enrich(ann)}), 201


# ── 获取单条 ──────────────────────────────────────────────────────
@bp.route("/<int:aid>", methods=["GET"])
@login_required
def get_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    if not _scope_ok(project):
        return jsonify({"ok": False, "error": "无权查看"}), 403
    return jsonify({"ok": True, "data": _enrich(ann)})


# ── 更新 ──────────────────────────────────────────────────────────
@bp.route("/<int:aid>", methods=["PUT"])
@login_required
def update_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    if not _can_edit(project):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认" and not _can_confirm(project):
        return jsonify({"ok": False, "error": "公告已确认，如需修改请联系经办人"}), 403

    data = request.get_json(force=True) or {}
    _apply_fields(ann, data)
    if ann.status == "待确认" and session.get("role") == "agency":
        ann.status = "草稿"
    _sync_project_round(project)
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
    if not _can_edit(project):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认" and not _can_confirm(project):
        return jsonify({"ok": False, "error": "已确认的公告无法删除，请联系经办人"}), 403

    # 同时删除附件文件
    attachments = db.session.execute(
        db.select(AnnouncementAttachment).where(AnnouncementAttachment.announcement_id == aid)
    ).scalars().all()
    for att in attachments:
        _delete_file(att)
        db.session.delete(att)

    db.session.delete(ann)
    _sync_project_round(project)
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
    if not _can_edit(project):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认":
        return jsonify({"ok": False, "error": "公告已经确认，无需重复提交"}), 400
    # 被驳回后再提交，记为「修改后重新提交」，与首次提交区分，归档时能看出改了几轮
    was_rejected = ann.status == "已驳回"
    ann.status = "待确认"
    alog.log(ann.project_id, _node_of(ann), "resubmit" if was_rejected else "submit",
             round_number=ann.round_number or 1, target_id=ann.id)
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交，等待经办人确认", "data": _enrich(ann)})


# ── 驳回（经办人打回代理机构修改）────────────────────────────────
@bp.route("/<int:aid>/reject", methods=["POST"])
@login_required
def reject_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    if not _can_confirm(project):
        return jsonify({"ok": False, "error": "仅本项目经办人或负责人可驳回"}), 403
    if ann.status == "已确认":
        return jsonify({"ok": False, "error": "公告已发布，如需修改请先撤回"}), 400
    reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "请填写驳回原因"}), 400

    ann.status = "已驳回"
    ann.reject_reason = reason
    ann.reject_count = int(ann.reject_count or 0) + 1
    ann.rejected_by = session.get("display_name", "")
    ann.rejected_at = datetime.datetime.now().isoformat(timespec="seconds")
    alog.log(ann.project_id, _node_of(ann), "reject",
             round_number=ann.round_number or 1, target_id=ann.id, reason=reason)
    db.session.commit()
    return jsonify({"ok": True,
                    "message": f"已驳回（第{ann.reject_count}次），代理机构可修改后重新提交",
                    "data": _enrich(ann)})


# ── 确认/发布 ─────────────────────────────────────────────────────
@bp.route("/<int:aid>/confirm", methods=["POST"])
@login_required
def confirm_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    if not _can_confirm(project):
        return jsonify({"ok": False, "error": "仅本项目经办人或负责人可确认发布"}), 403
    if ann.status == "已确认":
        return jsonify({"ok": False, "error": "公告已经发布"}), 400
    if ann.ann_type == "procurement" and project and not project.doc_confirmed:
        return jsonify({"ok": False, "error": "采购文件尚未确认，无法挂网发布"}), 400
    now = datetime.datetime.now().isoformat(timespec="seconds")
    ann.status = "已确认"
    ann.confirmed_by = session.get("display_name", "")
    ann.confirmed_at = now
    alog.log(ann.project_id, _node_of(ann), "confirm",
             round_number=ann.round_number or 1, target_id=ann.id)

    synced_msg = ""
    if ann.ann_type == "correction" and ann.response_deadline:
        # ── 更正公告调整了截止时间：强制同步项目开标时间 + 原采购公告截止时间 ──
        # （开标管理列表读的是原采购公告的 response_deadline，必须一并更新）
        project = db.session.get(Project, ann.project_id)
        if project:
            project.bid_time = ann.response_deadline
        src = db.session.execute(
            db.select(Announcement).where(
                Announcement.project_id == ann.project_id,
                Announcement.ann_type == "procurement",
                Announcement.round_number == (ann.round_number or 1),
                Announcement.status == "已确认",
            )
        ).scalars().first()
        if src:
            src.response_deadline = ann.response_deadline
        synced_msg = f"，截止时间已同步更正为 {ann.response_deadline}"
    elif ann.response_deadline:
        # ── 采购公告：自动将响应截止时间（开标时间）同步到项目 ────────
        project = db.session.get(Project, ann.project_id)
        if project and not project.bid_time:
            # 只在项目尚无开标时间时才自动填入，避免覆盖手动设置
            project.bid_time = ann.response_deadline

    db.session.commit()
    return jsonify({"ok": True, "message": f"公告已发布{synced_msg or '，开标时间已同步至项目'}",
                    "data": _enrich(ann)})


# ── 撤回确认 ──────────────────────────────────────────────────────
@bp.route("/<int:aid>/revoke", methods=["POST"])
@login_required
def revoke_announcement(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    if not _can_confirm(project):
        return jsonify({"ok": False, "error": "仅本项目经办人或负责人可撤回确认"}), 403
    ann.status = "草稿"
    ann.confirmed_by = ""
    ann.confirmed_at = ""
    alog.log(ann.project_id, _node_of(ann), "revoke",
             round_number=ann.round_number or 1, target_id=ann.id)
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
    if not _scope_ok(project):
        return jsonify({"ok": False, "error": "无权访问"}), 403
    if not project.agency_code:
        return jsonify({"ok": False, "error": "项目未关联代理机构"}), 400

    agency_name = _get_agency_name(project.agency_code)
    try:
        buf, filename = _generate_word_buf(project, ann, agency_name)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500


@bp.route("/<int:aid>/word", methods=["GET"])
@login_required
def preview_word(aid):
    """在线预览生成的公告 Word（任意状态，点项目名调用）。"""
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    project = db.session.get(Project, ann.project_id)
    if not _scope_ok(project):
        return jsonify({"ok": False, "error": "无权访问"}), 403
    if not project.agency_code:
        return jsonify({"ok": False, "error": "项目未关联代理机构"}), 400

    agency_name = _get_agency_name(project.agency_code)
    try:
        buf, filename = _generate_word_buf(project, ann, agency_name)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=False,
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
    if not _can_edit(project):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    if ann.status == "已确认" and not _can_confirm(project):
        return jsonify({"ok": False, "error": "公告已确认，无法上传附件"}), 403

    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
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
    if not _scope_ok(db.session.get(Project, ann.project_id)):
        return jsonify({"ok": False, "error": "无权访问"}), 403
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
    ann = db.session.get(Announcement, aid)
    if not _scope_ok(db.session.get(Project, ann.project_id) if ann else None):
        return jsonify({"ok": False, "error": "无权访问"}), 403
    path = os.path.join(_file_dir(aid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


# 内联预览附件（PDF/图片浏览器渲染，docx/xlsx 前端渲染）
@bp.route("/<int:aid>/files/<int:fid>/preview", methods=["GET"])
@login_required
def preview_file(aid, fid):
    att = db.session.get(AnnouncementAttachment, fid)
    if not att or att.announcement_id != aid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    ann = db.session.get(Announcement, aid)
    if not _scope_ok(db.session.get(Project, ann.project_id) if ann else None):
        return jsonify({"ok": False, "error": "无权访问"}), 403
    path = os.path.join(_file_dir(aid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    from services.office_convert import send_preview
    return send_preview(path, att.original_name)


# 删除附件
@bp.route("/<int:aid>/files/<int:fid>", methods=["DELETE"])
@login_required
def delete_file(aid, fid):
    att = db.session.get(AnnouncementAttachment, fid)
    if not att or att.announcement_id != aid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    ann = db.session.get(Announcement, aid)
    project = db.session.get(Project, ann.project_id) if ann else None
    if not _can_edit(project):
        return jsonify({"ok": False, "error": "权限不足"}), 403
    _delete_file(att)
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ── 项目列表（供前端选择） ──────────────────────────────────────
@bp.route("/projects", methods=["GET"])
@login_required
def eligible_projects():
    """可编制采购公告的项目：仅院内竞选/单一来源，当前轮采购文件已确认，且本轮尚未发过公告。

    - 项目层面的 doc_confirmed 跟随当前轮次——进入下一轮时被清零（见采购结果确认
      驱动的开轮逻辑），因此 doc_confirmed==1 即「已确认第 X 次采购文件」。
    - 每轮只能发一次：当前轮（Project.round）已存在采购公告（草稿/待确认/已确认任一）
      的项目即排除，发布后即从下拉消失；废标进入下一轮、重新确认文件后才会再出现。
    """
    role = session.get("role", "")
    my_agency = session.get("agency_code", "")
    ann_type = request.args.get("type", "procurement")

    if ann_type == "correction":
        # 可发更正公告的项目：本轮采购公告已发布（已确认）且「仍处开标前」（与开标管理 active 口径一致）。
        # 注意：「可开标」确认可发生在开标时间之前，此时项目仍是开标前、可更正——不能仅凭
        # can_open_status=='已确认' 就排除（旧逻辑的 bug，导致下拉为空）。
        from models.procurement_round import ProcurementRound
        from services.bid import _parse_cn_deadline
        from datetime import datetime as _dtnow
        pairs = db.session.execute(
            scope_projects(db.select(Project, Announcement))
            .join(Announcement, db.and_(
                Announcement.project_id == Project.id,
                Announcement.ann_type == "procurement",
                Announcement.round_number == db.func.coalesce(Project.round, 1),
                Announcement.status == "已确认",
            ))
            .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
            .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
            .where(Project.agency_code != "")
            .order_by(Project.id.desc())
        ).all()
        pids = list({p.id for p, _ in pairs})
        rmap = {}
        for r in db.session.execute(
            db.select(ProcurementRound).where(ProcurementRound.project_id.in_(pids or [0]))
        ).scalars().all():
            rmap[(r.project_id, r.round_number or 1)] = r
        rows, _seen = [], set()
        for p, a in pairs:
            if p.id in _seen:
                continue
            rnd = rmap.get((p.id, p.round or 1))
            # 只保留开标前(active)：流标已确认、或可开标且开标时间已过 → 已开标，排除
            if rnd and rnd.can_open_status == "已确认":
                if rnd.can_open != "可开标":
                    continue
                ddl = _parse_cn_deadline(a.response_deadline or p.bid_time or "")
                if ddl is None or _dtnow.now().date() > ddl.date():
                    continue
            rows.append(p)
            _seen.add(p.id)
    elif ann_type in ("survey", "single_source"):
        # 调研公告发生在采购需求论证阶段，单一来源公示发生在确定方式之后、
        # 采购文件确认之前——两者都**不能**要求「采购文件已确认」，
        # 否则下拉永远是空的。这里只要求项目本身有效。
        q = scope_projects(db.select(Project))
        q = (q
             .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
             .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None))))
        if ann_type == "single_source":
            # 单一来源公示只对单一来源类项目有意义
            q = q.where(db.or_(Project.method.like("%单一来源%"),
                               Project.method.like("%单一%")))
        rows = db.session.execute(q.order_by(Project.id.desc())).scalars().all()
    else:
        rows = db.session.execute(
            scope_projects(db.select(Project))
            .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
            .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
            .where(Project.agency_code != "")
            .where(Project.method.in_(ANNOUNCEMENT_REQUIRED_METHODS))
            .where(Project.doc_confirmed == 1)
            .where(~db.exists().where(db.and_(
                Announcement.project_id == Project.id,
                Announcement.ann_type == "procurement",
                Announcement.round_number == db.func.coalesce(Project.round, 1),
            )))
            .order_by(Project.id.desc())
        ).scalars().all()
    my_officer = session.get("display_name", "")
    result = []
    for p in rows:
        if role == "agency" and p.agency_code != my_agency:
            continue
        # 经办人隔离：officer 只看自己名下的项目；助理/负责人/管理员看全部
        if role == "officer" and (p.officer or "") != my_officer:
            continue
        result.append({
            "id": p.id,
            "name": p.name,
            "number": p.number,
            "agency_code": p.agency_code,
            "agency_name": _get_agency_name(p.agency_code),
            "status": p.status,
            "round": p.round or 1,
        })
    return jsonify({"ok": True, "data": result})
