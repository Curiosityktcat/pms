"""
询/议价函 API  —  /api/inquiries
系统配置 API   —  /api/sys-config
"""
import datetime
import os
import time
from io import BytesIO

from flask import Blueprint, request, session, jsonify, send_file

from models import db
from models.inquiry_letter import InquiryLetter
from models.inquiry_supplier import InquirySupplier
from models.inquiry_attachment import InquiryAttachment
from models.inquiry_template import InquiryTemplate
from models.project import Project
from models.sys_config import SysConfig
from routes.utils import login_required, admin_required, can_view_project
from services import upload_relay
from services.dept_scope import assert_can_view_project, scope_by_project

HERE = os.path.dirname(os.path.abspath(__file__))
PMS_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ATTACH_DIR = os.path.join(PMS_ROOT, '询价附件', '上传')
TMPL_DIR   = os.path.join(PMS_ROOT, '询价附件', '模板')
ATTACH_ALLOWED = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.zip', '.rar'}

bp = Blueprint("inquiry", __name__)

# 仅以下采购方式可立询/议价函（紧急采购按院内议价办理）
INQUIRY_METHODS = ("院内询价", "院内议价", "医用耗材紧急采购")

# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────


def _inquiry_ineligible_reason(project_id):
    """校验项目是否可立询/议价函：方式须为询/议价/紧急采购，且未处于进行中的采购轮次。

    与下拉过滤口径一致——已进入轮次且本轮未废标的项目不可立项；
    无轮次（尚未开始）或本轮已废标（待开下一轮）的方可。
    """
    proj = db.session.get(Project, project_id)
    if not proj:
        return "项目不存在"
    if (proj.method or "") not in INQUIRY_METHODS:
        return "仅院内询价/院内议价/医用耗材紧急采购项目可立询/议价函"
    from services.project_progress import stage_map
    st = stage_map([project_id]).get(project_id, {})
    if st.get("current_round", 0) and st.get("current_stage", "") != "round_failed":
        return "该项目已进入采购轮次（本轮未废标），不可重复立项"
    return None

def _block_if_deleted(letter):
    """项目已软删除则禁止对其询/议价函进一步操作。返回错误响应或 None。"""
    proj = db.session.get(Project, letter.project_id) if letter else None
    if proj is not None and proj.is_deleted:
        return jsonify({"ok": False, "error": "所属项目已删除，不可继续操作"}), 400
    return None


def _scoped_letter(lid):
    """取询/议价函并做归属校验（officer 本人经办 / agency 本机构 / 助理·负责人·管理员）。
    返回 (letter, error)；error 非空时应直接 return。"""
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return None, (jsonify({"ok": False, "error": "不存在"}), 404)
    if session.get("role") in ("dept", "dept_manage", "dept_demand"):
        assert_can_view_project(letter.project_id)
        return letter, None
    if not can_view_project(db.session.get(Project, letter.project_id)):
        return None, (jsonify({"ok": False, "error": "无权访问该询/议价函"}), 403)
    return letter, None


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _enrich_letter(letter: InquiryLetter) -> dict:
    """给函件 dict 补充项目信息"""
    d = letter.to_dict()
    proj = db.session.get(Project, letter.project_id)
    d["project_name"]   = proj.name if proj else ""
    d["project_number"] = proj.number if proj else ""

    # 统计供应商
    suppliers = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=letter.id)
    ).scalars().all()
    d["supplier_count"] = len(suppliers)
    d["sent_count"]     = sum(1 for s in suppliers if s.sent_at)
    return d


# ─────────────────────────────────────────────────────────────────
# 询/议价函 CRUD
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries", methods=["GET"])
@login_required
def list_inquiries():
    project_id = request.args.get("project_id", type=int)
    # 排除已被软删除项目的函——项目删除后其询/议价函不再展示、不可操作
    q = (scope_by_project(db.select(InquiryLetter), InquiryLetter)
         .join(Project, Project.id == InquiryLetter.project_id)
         .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
         .order_by(InquiryLetter.id.desc()))
    if project_id:
        q = q.filter(InquiryLetter.project_id == project_id)
    rows = db.session.execute(q).scalars().all()
    # 数据级隔离：经办人只看本人项目的函、代理只看本机构（与项目列表口径一致）
    if session.get("role") not in ("dept", "dept_manage", "dept_demand"):
        rows = [r for r in rows if can_view_project(db.session.get(Project, r.project_id))]
    return jsonify({"ok": True, "data": [_enrich_letter(r) for r in rows]})


@bp.route("/api/inquiries", methods=["POST"])
@login_required
def create_inquiry():
    data = request.get_json(force=True) or {}
    now = _now()
    letter = InquiryLetter(
        project_id = data.get("project_id"),
        type       = data.get("type", "询价"),
        title      = data.get("title", ""),
        content    = data.get("content", ""),
        detail     = data.get("detail", ""),
        requirements = data.get("requirements", ""),
        deadline   = data.get("deadline", ""),
        status     = "待办",
        notes      = data.get("notes", ""),
        created_by = session.get("display_name", ""),
        created_at = now,
        updated_at = now,
    )
    if not letter.project_id:
        return jsonify({"ok": False, "error": "请选择所属项目"}), 400
    reason = _inquiry_ineligible_reason(letter.project_id)
    if reason:
        return jsonify({"ok": False, "error": reason}), 400
    db.session.add(letter)
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich_letter(letter)}), 201


@bp.route("/api/inquiries/<int:lid>", methods=["PUT"])
@login_required
def update_inquiry(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    blocked = _block_if_deleted(letter)
    if blocked:
        return blocked
    # 待办与进行中均可改（如发现预算/限价填错，可修正后重新发送）；已完成（评审已出结果）锁定
    if letter.status == "已完成":
        return jsonify({"ok": False, "error": "已完成的函件不可编辑"}), 400
    data = request.get_json(force=True) or {}
    for field in ("type", "title", "content", "detail", "requirements", "deadline", "notes"):
        if field in data:
            setattr(letter, field, data[field])
    if "project_id" in data and data["project_id"] != letter.project_id:
        reason = _inquiry_ineligible_reason(data["project_id"])
        if reason:
            return jsonify({"ok": False, "error": reason}), 400
        letter.project_id = data["project_id"]
    letter.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich_letter(letter)})


@bp.route("/api/inquiries/<int:lid>", methods=["DELETE"])
@login_required
def delete_inquiry(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    if letter.status != "待办":
        return jsonify({"ok": False, "error": "仅待办状态可删除"}), 400
    # 级联删除供应商
    db.session.execute(
        db.delete(InquirySupplier).where(InquirySupplier.inquiry_id == lid)
    )
    # 级联删除附件：**记录和磁盘文件都要删**。只删记录会留下孤儿文件；只删函件不删附件，
    # 则因为 SQLite 会复用被删记录的 id，下一封新建的函件会"继承"上一封的附件（实测过）。
    _atts = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=lid)
    ).scalars().all()
    for _a in _atts:
        try:
            _fp = os.path.join(PMS_ROOT, _a.filepath or "")
            if _a.filepath and os.path.exists(_fp):
                os.remove(_fp)
        except OSError:
            pass          # 文件删不掉不阻断删记录，避免留下"看得见删不掉"的僵尸函件
        db.session.delete(_a)
    # 供应商上传的响应文件同理
    try:
        from models.inquiry_review import InquirySupplierFile as _ISF   # 模型定义在 inquiry_review.py 里
        _sfs = db.session.execute(db.select(_ISF).filter_by(inquiry_id=lid)).scalars().all()
        for _sf in _sfs:
            try:
                _sfp = os.path.join(PMS_ROOT, _sf.filepath or "")
                if _sf.filepath and os.path.exists(_sfp):
                    os.remove(_sfp)
            except OSError:
                pass
            db.session.delete(_sf)
    except ImportError:
        pass
    db.session.delete(letter)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/api/inquiries/<int:lid>/complete", methods=["POST"])
@login_required
def complete_inquiry(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    blocked = _block_if_deleted(letter)
    if blocked:
        return blocked
    letter.status     = "已完成"
    letter.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已标记为完成", "data": _enrich_letter(letter)})


@bp.route("/api/inquiries/<int:lid>/word", methods=["GET"])
@login_required
def download_word(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    proj = db.session.get(Project, letter.project_id)
    project_name   = proj.name    if proj else ""
    project_number = proj.number  if proj else ""
    officer        = proj.officer if proj else ""

    from services.inquiry_word import generate_inquiry_word
    buf = generate_inquiry_word(letter, project_name, project_number, officer)

    safe_title = (letter.title or f"{letter.type}邀请函").replace("/", "-")
    filename   = f"{safe_title}.docx"

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@bp.route("/api/inquiries/<int:lid>/word/preview", methods=["GET"])
@login_required
def preview_word(lid):
    """在线预览生成的询/议价邀请函（内联，前端 docx-preview 渲染）"""
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    proj = db.session.get(Project, letter.project_id)
    project_name   = proj.name    if proj else ""
    project_number = proj.number  if proj else ""
    officer        = proj.officer if proj else ""

    from services.inquiry_word import generate_inquiry_word
    buf = generate_inquiry_word(letter, project_name, project_number, officer)

    safe_title = (letter.title or f"{letter.type}邀请函").replace("/", "-")
    return send_file(
        buf,
        as_attachment=False,
        download_name=f"{safe_title}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ─────────────────────────────────────────────────────────────────
# 供应商子路由
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/suppliers", methods=["GET"])
@login_required
def list_suppliers(lid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    suppliers = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=lid).order_by(InquirySupplier.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [s.to_dict() for s in suppliers]})


@bp.route("/api/inquiries/<int:lid>/suppliers", methods=["POST"])
@login_required
def add_supplier(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    blocked = _block_if_deleted(letter)
    if blocked:
        return blocked
    data = request.get_json(force=True) or {}
    sup = InquirySupplier(
        inquiry_id    = lid,
        supplier_name = data.get("supplier_name", ""),
        contact_name  = data.get("contact_name", ""),
        contact_phone = data.get("contact_phone", ""),
        email         = data.get("email", ""),
    )
    db.session.add(sup)
    db.session.commit()
    return jsonify({"ok": True, "data": sup.to_dict()}), 201


def _norm(s):
    import re
    return re.sub(r"[\s_\-（）()【】\[\].,，。、:：;；'\"]", "", (s or "")).lower()


@bp.route("/api/inquiries/<int:lid>/replies", methods=["GET"])
@login_required
def inquiry_replies(lid):
    """从收件箱抓取本询价（项目名称+轮次）的供应商回复，标注谁回了。

    匹配按固定格式『项目名称_第N次_供应商全称』：主题含供应商名→该家已回复，
    含项目名→确信是本项目。格式不规范的旧回复尽力匹配，匹配不上的列为待人工归类。
    """
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    _, proj_name, rnd = _reply_subject_format(letter)
    sups = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=lid)).scalars().all()

    try:
        from services.email_service import fetch_inbox
        mails = fetch_inbox(limit=300)
    except Exception as e:
        return jsonify({"ok": False, "error": f"收信失败：{e}"}), 502

    np = _norm(proj_name)
    for m in mails:
        m["_ns"] = _norm(m["subject"])
        m["_proj"] = bool(np) and np in m["_ns"]   # 主题含项目名=确信本项目

    rows, matched_idx = [], set()
    for s in sups:
        nsup = _norm(s.supplier_name)
        nemail = (s.email or "").strip().lower()
        best = None
        for i, m in enumerate(mails):
            name_hit = bool(nsup) and nsup in m["_ns"]
            mail_hit = bool(nemail) and nemail == (m["from_addr"] or "").lower()
            if name_hit or mail_hit:
                cand = {"i": i, "confident": m["_proj"], "subject": m["subject"],
                        "from": m["from_addr"], "date": m["date"]}
                if best is None or (cand["confident"] and not best["confident"]):
                    best = cand
                if cand["confident"]:
                    break
        d = s.to_dict()
        if best:
            matched_idx.add(best["i"])
            d["replied"] = True
            d["reply_subject"] = best["subject"]
            d["reply_from"] = best["from"]
            d["reply_date"] = best["date"]
            d["reply_confident"] = best["confident"]
        else:
            d["replied"] = False
        rows.append(d)

    # 主题含项目名但没匹配到任何供应商 → 待人工归类
    unmatched = [{"subject": m["subject"], "from": m["from_addr"], "date": m["date"]}
                 for i, m in enumerate(mails)
                 if m["_proj"] and i not in matched_idx]

    replied_n = sum(1 for d in rows if d["replied"])
    sent_n = sum(1 for s in sups if (s.email or "").strip())
    return jsonify({"ok": True, "data": {
        "project_name": proj_name, "round": rnd,
        "reply_format": f"{proj_name}_第{rnd}次_供应商全称",
        "replied": replied_n, "sent": sent_n,
        "suppliers": rows, "unmatched": unmatched,
    }})


@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>", methods=["PUT"])
@login_required
def update_supplier(lid, sid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    sup = db.session.get(InquirySupplier, sid)
    if not sup or sup.inquiry_id != lid:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data = request.get_json(force=True) or {}
    for field in (
        "supplier_name", "contact_name", "contact_phone", "email",
        "quote_amount", "quote_date", "quote_note", "is_selected",
    ):
        if field in data:
            setattr(sup, field, data[field])
    db.session.commit()
    return jsonify({"ok": True, "data": sup.to_dict()})


@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>", methods=["DELETE"])
@login_required
def delete_supplier(lid, sid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    sup = db.session.get(InquirySupplier, sid)
    if not sup or sup.inquiry_id != lid:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if sup.sent_at:
        return jsonify({"ok": False, "error": "已发送邮件的供应商不可删除"}), 400
    db.session.delete(sup)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


# ─── 邮件发送辅助（单发 / 群发共用）──────────────────────────────

def _reply_subject_format(letter, supplier_name=None):
    """供应商回复邮件应使用的固定主题：项目名称_第N次_供应商全称。
    用项目名称（非编号，供应商更易识别）+ 采购轮次，便于系统按格式抓取归类。
    返回 (示例主题, 项目名称, 轮次)。"""
    proj = db.session.get(Project, letter.project_id)
    name = (proj.name if proj else "") or ""
    rnd = (proj.round if proj else 1) or 1
    return f"{name}_第{rnd}次_{supplier_name or '贵公司全称'}", name, rnd


def _build_supplier_email_body(letter, sup, project_name, project_number, receive_email):
    """构建发给某供应商的邮件正文（HTML）—— 与 Word 公告体例保持一致"""
    def _h(s):
        return (s or "").replace("\n", "<br/>")
    fmt_example, _, _ = _reply_subject_format(letter, sup.supplier_name or "贵公司全称")
    reply_notice = (
        "<div style='margin:16px 0; padding:12px 16px; background:#fff7e6; border:1px solid #ffd591;'>"
        "<p style='color:#c00; font-weight:bold; margin:0 0 6px;'>⚠ 回复须知（务必遵守，否则可能导致报价漏收）</p>"
        "请将回复邮件的<strong>主题</strong>严格按以下格式填写（用下划线 _ 分隔三段）：<br/>"
        "<span style='display:inline-block; margin:6px 0; padding:6px 10px; background:#fff; "
        "border:1px dashed #faad14; font-weight:bold;'>项目名称_第N次_贵公司全称</span><br/>"
        "本项目请直接填写为：<br/>"
        f"<span style='display:inline-block; margin:6px 0; padding:6px 10px; background:#fff; "
        f"border:1px dashed #fa8c16; color:#c00; font-weight:bold;'>{fmt_example}</span>"
        "</div>"
    )
    deadline_text = (
        f"<br/><strong style='color:#c00'>资料请于 {letter.deadline} 前发送至 {receive_email}。</strong>"
        if letter.deadline else ""
    )
    return f"""
<html><body style="font-family: 微软雅黑,sans-serif; font-size:14px; color:#333; line-height:1.8;">
<h2 style="color:#1f3464; text-align:center;">{letter.title or (letter.type + '邀请函')}</h2>
<p>尊敬的 <strong>{sup.supplier_name or '供应商'}</strong>，</p>
<div style="margin:16px 0; padding:12px 16px; background:#f7f9fc; border-left:4px solid #1677ff;">
  <p><strong>项目名称：</strong>{project_name}</p>
  <p><strong>项目编号：</strong>{project_number}</p>
  <p><strong>函件类型：</strong>{letter.type}</p>
</div>
<div style="margin:16px 0;">
  <p><strong>项目细则和限价：</strong>{_h(letter.detail)}</p>
  <p><strong>相关要求：</strong>{_h(letter.requirements)}</p>
</div>
{reply_notice}
{deadline_text}
<br/>
<hr style="border:none;border-top:1px solid #eee;margin:20px 0;"/>
<p style="color:#888; font-size:12px;">
  本邮件由内江市第一人民医院采购部系统自动发送，请勿直接回复本邮件。<br/>
  如有疑问，请联系采购部。
</p>
<p style="text-align:right; color:#555;">
  <strong>内江市第一人民医院采购部</strong>
</p>
</body></html>
"""


def _prepare_letter_package(letter, proj):
    """生成本函件的 Word 正文与附件（同一函件群发时只生成一次）。
    返回 (project_name, project_number, subject, word_bytes, attachment_filename, extra_attachments)
    """
    project_name   = proj.name    if proj else ""
    project_number = proj.number  if proj else ""
    officer        = proj.officer if proj else ""

    from services.inquiry_word import generate_inquiry_word
    buf = generate_inquiry_word(letter, project_name, project_number, officer)
    word_bytes = buf.getvalue()   # 取 bytes，供多次发送复用（BytesIO 读一次即空）

    safe_title          = (letter.title or f"{letter.type}邀请函").replace("/", "-")
    attachment_filename = f"{safe_title}.docx"
    subject             = f"{letter.title or letter.type + '邀请函'} — {project_name}"

    ink_attachments = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=letter.id).order_by(InquiryAttachment.id)
    ).scalars().all()
    extra_attachments = []
    for att in ink_attachments:
        full_path = os.path.join(PMS_ROOT, att.filepath)
        if os.path.exists(full_path):
            with open(full_path, 'rb') as fh:
                extra_attachments.append((fh.read(), att.filename))

    return project_name, project_number, subject, word_bytes, attachment_filename, extra_attachments


def _send_letter_to(sup, letter, project_name, project_number, subject,
                    word_bytes, attachment_filename, extra_attachments):
    """向单个供应商发送邮件并记录发送信息（调用方负责 commit）。"""
    from services.email_service import send_email
    from services.inquiry_word import RECEIVE_EMAIL
    body_html = _build_supplier_email_body(letter, sup, project_name, project_number, RECEIVE_EMAIL)
    send_email(
        to_addr             = sup.email,
        subject             = subject,
        body_html           = body_html,
        attachment_bytes    = word_bytes,
        attachment_filename = attachment_filename,
        extra_attachments   = extra_attachments,
    )
    sup.sent_at = _now()
    sup.sent_by = session.get("display_name", "")


def _advance_status_if_all_sent(letter):
    """所有供应商均已发送时，把待办函件推进为「进行中」。"""
    all_suppliers = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=letter.id)
    ).scalars().all()
    if all_suppliers and all(s.sent_at for s in all_suppliers):
        if letter.status == "待办":
            letter.status     = "进行中"
            letter.updated_at = _now()
            db.session.commit()


def _xunjia_email_ok(letter):
    """询价函要求至少 3 家填写邮箱；返回 (是否满足, 已填邮箱家数)"""
    if letter.type != "询价":
        return True, None
    all_sups = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=letter.id)
    ).scalars().all()
    email_count = sum(1 for s in all_sups if s.email and s.email.strip())
    return email_count >= 3, email_count


@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>/send", methods=["POST"])
@login_required
def send_to_supplier(lid, sid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    blocked = _block_if_deleted(letter)
    if blocked:
        return blocked
    sup = db.session.get(InquirySupplier, sid)
    if not sup or sup.inquiry_id != lid:
        return jsonify({"ok": False, "error": "供应商不存在"}), 404
    if not sup.email:
        return jsonify({"ok": False, "error": "该供应商未填写邮箱地址"}), 400

    ok, email_count = _xunjia_email_ok(letter)
    if not ok:
        return jsonify({"ok": False, "error": f"询价函要求至少 3 家供应商填写邮箱地址，当前仅 {email_count} 家，请先补充"}), 400

    proj = db.session.get(Project, letter.project_id)
    project_name, project_number, subject, word_bytes, fname, extra = _prepare_letter_package(letter, proj)
    try:
        _send_letter_to(sup, letter, project_name, project_number, subject, word_bytes, fname, extra)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"邮件发送失败：{str(e)}"}), 500
    db.session.commit()
    _advance_status_if_all_sent(letter)

    return jsonify({
        "ok": True,
        "message": f"邮件已成功发送至 {sup.email}",
        "data": sup.to_dict(),
    })


@bp.route("/api/inquiries/<int:lid>/send-all", methods=["POST"])
@login_required
def send_all_suppliers(lid):
    """一键群发：把函件正文+附件发送给所有「已填邮箱且未发送」的供应商。"""
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    blocked = _block_if_deleted(letter)
    if blocked:
        return blocked
    if letter.status == "已完成":
        return jsonify({"ok": False, "error": "已完成的函件不可再发送"}), 400

    suppliers = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=lid).order_by(InquirySupplier.id)
    ).scalars().all()
    if not suppliers:
        return jsonify({"ok": False, "error": "请先在「编辑」中添加供应商"}), 400

    ok, email_count = _xunjia_email_ok(letter)
    if not ok:
        return jsonify({"ok": False, "error": f"询价函要求至少 3 家供应商填写邮箱地址，当前仅 {email_count} 家，请先补充"}), 400

    targets = [s for s in suppliers if s.email and s.email.strip() and not s.sent_at]
    if not targets:
        has_email = any(s.email and s.email.strip() for s in suppliers)
        if not has_email:
            return jsonify({"ok": False, "error": "供应商均未填写邮箱地址，请先补充"}), 400
        return jsonify({"ok": False, "error": "所有已填邮箱的供应商均已发送"}), 400

    proj = db.session.get(Project, letter.project_id)
    project_name, project_number, subject, word_bytes, fname, extra = _prepare_letter_package(letter, proj)

    sent, failed = [], []
    for sup in targets:
        try:
            _send_letter_to(sup, letter, project_name, project_number, subject, word_bytes, fname, extra)
            db.session.commit()              # 逐家提交，部分成功也能落库
            sent.append(sup.email)
        except ValueError as e:
            # 配置类错误对所有供应商都一样，直接中止
            db.session.rollback()
            return jsonify({"ok": False, "error": str(e), "sent": sent, "failed": failed}), 400
        except Exception as e:
            db.session.rollback()
            failed.append({"email": sup.email, "error": str(e)})

    _advance_status_if_all_sent(letter)

    msg = f"成功发送 {len(sent)} 家"
    if failed:
        msg += f"，失败 {len(failed)} 家"
    return jsonify({
        "ok": True,
        "message": msg,
        "sent": sent,
        "failed": failed,
        "data": _enrich_letter(letter),
    })


# ─────────────────────────────────────────────────────────────────
# 附件管理
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/attachments", methods=["GET"])
@login_required
def list_inquiry_attachments(lid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    atts = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=lid).order_by(InquiryAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [a.to_dict() for a in atts]})


@bp.route("/api/inquiries/<int:lid>/attachments", methods=["POST"])
@login_required
def upload_inquiry_attachment(lid):
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ATTACH_ALLOWED:
        return jsonify({"ok": False, "error": f"不支持的文件格式 {ext}，允许：pdf/doc/docx/xls/xlsx/jpg/png/zip/rar"}), 400

    os.makedirs(ATTACH_DIR, exist_ok=True)
    safe_name = f"{lid}_{int(time.time())}{ext}"
    save_path = os.path.join(ATTACH_DIR, safe_name)
    f.save(save_path)

    att = InquiryAttachment(
        inquiry_id  = lid,
        filename    = f.filename,
        filepath    = f"询价附件/上传/{safe_name}",
        uploaded_at = _now(),
        uploaded_by = session.get("display_name", ""),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "data": att.to_dict()}), 201


@bp.route("/api/inquiries/<int:lid>/attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete_inquiry_attachment(lid, aid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    att = db.session.get(InquiryAttachment, aid)
    if not att or att.inquiry_id != lid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    # 删除文件
    full_path = os.path.join(PMS_ROOT, att.filepath)
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


def _inquiry_attachment_path(lid, aid):
    """返回 (att, 绝对路径) 或 (None, None)"""
    att = db.session.get(InquiryAttachment, aid)
    if not att or att.inquiry_id != lid:
        return None, None
    full_path = os.path.join(PMS_ROOT, att.filepath)
    if not os.path.exists(full_path):
        return att, None
    return att, full_path


@bp.route("/api/inquiries/<int:lid>/attachments/<int:aid>/download", methods=["GET"])
@login_required
def download_inquiry_attachment(lid, aid):
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    att, path = _inquiry_attachment_path(lid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(path, as_attachment=True, download_name=att.filename)


@bp.route("/api/inquiries/<int:lid>/attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview_inquiry_attachment(lid, aid):
    """内联预览（PDF/图片浏览器渲染，docx/xlsx 前端渲染）"""
    _letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    att, path = _inquiry_attachment_path(lid, aid)
    if not att:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    from services.office_convert import send_preview
    return send_preview(path, att.filename)


# ─────────────────────────────────────────────────────────────────
# 附件模板库
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiry-templates", methods=["GET"])
@login_required
def list_templates():
    rows = db.session.execute(
        db.select(InquiryTemplate).order_by(InquiryTemplate.id.desc())
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/api/inquiry-templates", methods=["POST"])
@login_required
def upload_template():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ATTACH_ALLOWED:
        return jsonify({"ok": False, "error": f"不支持的文件格式 {ext}"}), 400

    description = request.form.get("description", "").strip()
    os.makedirs(TMPL_DIR, exist_ok=True)
    safe_name = f"{int(time.time())}{ext}"
    save_path = os.path.join(TMPL_DIR, safe_name)
    f.save(save_path)

    tmpl = InquiryTemplate(
        filename    = f.filename,
        description = description,
        filepath    = f"询价附件/模板/{safe_name}",
        uploaded_at = _now(),
        uploaded_by = session.get("display_name", ""),
    )
    db.session.add(tmpl)
    db.session.commit()
    return jsonify({"ok": True, "data": tmpl.to_dict()}), 201


def _template_path(tid):
    """返回 (模板, 绝对路径)；文件丢了路径为 None。"""
    tmpl = db.session.get(InquiryTemplate, tid)
    if not tmpl:
        return None, None
    full = os.path.join(PMS_ROOT, tmpl.filepath or "")
    return tmpl, (full if tmpl.filepath and os.path.exists(full) else None)


@bp.route("/api/inquiry-templates/<int:tid>/preview", methods=["GET"])
@login_required
def preview_template(tid):
    """模板内联预览（doc/ppt 等自动转 PDF；docx/xlsx 交前端渲染）"""
    tmpl, path = _template_path(tid)
    if not tmpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    from services.office_convert import send_preview
    return send_preview(path, tmpl.filename)


@bp.route("/api/inquiry-templates/<int:tid>/download", methods=["GET"])
@login_required
def download_template(tid):
    tmpl, path = _template_path(tid)
    if not tmpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not path:
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(path, as_attachment=True, download_name=tmpl.filename)


@bp.route("/api/inquiry-templates/<int:tid>", methods=["PUT"])
@login_required
def update_template(tid):
    tmpl = db.session.get(InquiryTemplate, tid)
    if not tmpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    data = request.get_json(force=True) or {}
    if "description" in data:
        tmpl.description = data["description"].strip()
    db.session.commit()
    return jsonify({"ok": True, "data": tmpl.to_dict()})


@bp.route("/api/inquiry-templates/<int:tid>", methods=["DELETE"])
@login_required
def delete_template(tid):
    tmpl = db.session.get(InquiryTemplate, tid)
    if not tmpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    full_path = os.path.join(PMS_ROOT, tmpl.filepath)
    if os.path.exists(full_path):
        try:
            os.remove(full_path)
        except OSError:
            pass
    db.session.delete(tmpl)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/api/inquiries/<int:lid>/attachments/from-template", methods=["POST"])
@login_required
def attach_from_template(lid):
    """将模板库中的文件复制为本函件的附件（独立副本，互不影响）"""
    letter, _serr = _scoped_letter(lid)
    if _serr:
        return _serr
    data = request.get_json(force=True) or {}
    template_ids = data.get("template_ids", [])
    if not template_ids:
        return jsonify({"ok": False, "error": "未选择模板"}), 400

    os.makedirs(ATTACH_DIR, exist_ok=True)
    created = []
    for tid in template_ids:
        tmpl = db.session.get(InquiryTemplate, int(tid))
        if not tmpl:
            continue
        src = os.path.join(PMS_ROOT, tmpl.filepath)
        if not os.path.exists(src):
            continue
        ext = os.path.splitext(tmpl.filename)[1].lower()
        safe_name = f"{lid}_{int(time.time())}_{tmpl.id}{ext}"
        dst = os.path.join(ATTACH_DIR, safe_name)
        import shutil
        shutil.copy2(src, dst)
        att = InquiryAttachment(
            inquiry_id  = lid,
            filename    = tmpl.filename,
            filepath    = f"询价附件/上传/{safe_name}",
            uploaded_at = _now(),
            uploaded_by = session.get("display_name", "") + "（模板库）",
        )
        db.session.add(att)
        created.append(tmpl.filename)

    db.session.commit()
    return jsonify({"ok": True, "message": f"已添加 {len(created)} 个模板附件", "added": created})


# ─────────────────────────────────────────────────────────────────
# 系统配置 — 邮件
# ─────────────────────────────────────────────────────────────────

EMAIL_KEYS = [
    "email_smtp_host",
    "email_smtp_port",
    "email_address",
    "email_auth_code",
    "email_sender_name",
]


@bp.route("/api/sys-config/email", methods=["GET"])
@admin_required
def get_email_config():
    result = {}
    for k in EMAIL_KEYS:
        row = db.session.get(SysConfig, k)
        val = row.value if row else ""
        # 对 auth_code 脱敏：仅显示后 4 位
        if k == "email_auth_code" and val:
            val = "****" + val[-4:]
        result[k] = val
    return jsonify({"ok": True, "data": result})


@bp.route("/api/sys-config/email", methods=["PUT"])
@admin_required
def update_email_config():
    data = request.get_json(force=True) or {}
    now  = _now()
    for k in EMAIL_KEYS:
        if k not in data:
            continue
        val = data[k]
        # 若 auth_code 是脱敏值（****xxxx），跳过不更新
        if k == "email_auth_code" and isinstance(val, str) and val.startswith("****"):
            continue
        row = db.session.get(SysConfig, k)
        if row:
            row.value      = val
            row.updated_at = now
        else:
            db.session.add(SysConfig(key=k, value=val, updated_at=now))
    db.session.commit()
    return jsonify({"ok": True, "message": "邮件配置已保存"})


@bp.route("/api/sys-config/email/test", methods=["POST"])
@admin_required
def test_email():
    from services.email_service import get_email_config, send_email
    cfg = get_email_config()
    to_addr = cfg.get("email_address", "")
    if not to_addr:
        return jsonify({"ok": False, "error": "请先配置发件邮箱"}), 400

    body_html = """
<html><body style="font-family:微软雅黑,sans-serif;font-size:14px;color:#333;">
<h3 style="color:#1677ff;">邮件发送测试</h3>
<p>这是来自<strong>内江市第一人民医院采购管理系统</strong>的测试邮件。</p>
<p>如果您收到此邮件，说明邮件配置正确。</p>
<p style="color:#888;font-size:12px;margin-top:20px;">内江市第一人民医院采购部</p>
</body></html>
"""
    try:
        send_email(
            to_addr   = to_addr,
            subject   = "邮件配置测试",
            body_html = body_html,
        )
        return jsonify({"ok": True, "message": f"测试邮件已发送至 {to_addr}"})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"发送失败：{str(e)}"}), 500
