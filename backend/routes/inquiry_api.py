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
from routes.utils import login_required, admin_required

HERE = os.path.dirname(os.path.abspath(__file__))
PMS_ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
ATTACH_DIR = os.path.join(PMS_ROOT, '询价附件', '上传')
TMPL_DIR   = os.path.join(PMS_ROOT, '询价附件', '模板')
ATTACH_ALLOWED = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.zip', '.rar'}

bp = Blueprint("inquiry", __name__)

# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────

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
    q = db.select(InquiryLetter).order_by(InquiryLetter.id.desc())
    if project_id:
        q = q.filter(InquiryLetter.project_id == project_id)
    rows = db.session.execute(q).scalars().all()
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
        deadline   = data.get("deadline", ""),
        status     = "草稿",
        notes      = data.get("notes", ""),
        created_by = session.get("display_name", ""),
        created_at = now,
        updated_at = now,
    )
    if not letter.project_id:
        return jsonify({"ok": False, "error": "请选择所属项目"}), 400
    db.session.add(letter)
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich_letter(letter)}), 201


@bp.route("/api/inquiries/<int:lid>", methods=["PUT"])
@login_required
def update_inquiry(lid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if letter.status != "草稿":
        return jsonify({"ok": False, "error": "仅草稿状态可编辑"}), 400
    data = request.get_json(force=True) or {}
    for field in ("type", "title", "content", "deadline", "notes"):
        if field in data:
            setattr(letter, field, data[field])
    if "project_id" in data:
        letter.project_id = data["project_id"]
    letter.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich_letter(letter)})


@bp.route("/api/inquiries/<int:lid>", methods=["DELETE"])
@login_required
def delete_inquiry(lid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if letter.status != "草稿":
        return jsonify({"ok": False, "error": "仅草稿状态可删除"}), 400
    # 级联删除供应商
    db.session.execute(
        db.delete(InquirySupplier).where(InquirySupplier.inquiry_id == lid)
    )
    db.session.delete(letter)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/api/inquiries/<int:lid>/complete", methods=["POST"])
@login_required
def complete_inquiry(lid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "不存在"}), 404
    letter.status     = "已完成"
    letter.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已标记为完成", "data": _enrich_letter(letter)})


@bp.route("/api/inquiries/<int:lid>/word", methods=["GET"])
@login_required
def download_word(lid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "不存在"}), 404
    proj = db.session.get(Project, letter.project_id)
    project_name   = proj.name   if proj else ""
    project_number = proj.number if proj else ""

    from services.inquiry_word import generate_inquiry_word
    buf = generate_inquiry_word(letter, project_name, project_number)

    safe_title = (letter.title or f"{letter.type}邀请函").replace("/", "-")
    filename   = f"{safe_title}.docx"

    return send_file(
        buf,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


# ─────────────────────────────────────────────────────────────────
# 供应商子路由
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/suppliers", methods=["GET"])
@login_required
def list_suppliers(lid):
    suppliers = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=lid).order_by(InquirySupplier.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [s.to_dict() for s in suppliers]})


@bp.route("/api/inquiries/<int:lid>/suppliers", methods=["POST"])
@login_required
def add_supplier(lid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "函件不存在"}), 404
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


@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>", methods=["PUT"])
@login_required
def update_supplier(lid, sid):
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
    sup = db.session.get(InquirySupplier, sid)
    if not sup or sup.inquiry_id != lid:
        return jsonify({"ok": False, "error": "不存在"}), 404
    if sup.sent_at:
        return jsonify({"ok": False, "error": "已发送邮件的供应商不可删除"}), 400
    db.session.delete(sup)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})


@bp.route("/api/inquiries/<int:lid>/suppliers/<int:sid>/send", methods=["POST"])
@login_required
def send_to_supplier(lid, sid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "函件不存在"}), 404
    sup = db.session.get(InquirySupplier, sid)
    if not sup or sup.inquiry_id != lid:
        return jsonify({"ok": False, "error": "供应商不存在"}), 404
    if not sup.email:
        return jsonify({"ok": False, "error": "该供应商未填写邮箱地址"}), 400

    # 询价函：强制要求至少 3 家填写邮箱
    if letter.type == "询价":
        all_sups = db.session.execute(
            db.select(InquirySupplier).filter_by(inquiry_id=lid)
        ).scalars().all()
        email_count = sum(1 for s in all_sups if s.email and s.email.strip())
        if email_count < 3:
            return jsonify({
                "ok": False,
                "error": f"询价函要求至少 3 家供应商填写邮箱地址，当前仅 {email_count} 家，请先补充"
            }), 400

    # 生成 Word 附件
    proj = db.session.get(Project, letter.project_id)
    project_name   = proj.name   if proj else ""
    project_number = proj.number if proj else ""

    from services.inquiry_word import generate_inquiry_word
    buf = generate_inquiry_word(letter, project_name, project_number)

    safe_title     = (letter.title or f"{letter.type}邀请函").replace("/", "-")
    attachment_filename = f"{safe_title}.docx"

    # 构建邮件正文（HTML）
    deadline_text = f"<br/><strong style='color:#c00'>请于 {letter.deadline} 前回复报价。</strong>" if letter.deadline else ""
    content_html  = letter.content.replace("\n", "<br/>") if letter.content else ""

    body_html = f"""
<html><body style="font-family: 微软雅黑,sans-serif; font-size:14px; color:#333; line-height:1.8;">
<h2 style="color:#1f3464; text-align:center;">{letter.title or (letter.type + '邀请函')}</h2>
<p>尊敬的 <strong>{sup.supplier_name or '供应商'}</strong>，</p>
<div style="margin:16px 0; padding:12px 16px; background:#f7f9fc; border-left:4px solid #1677ff;">
  <p><strong>项目名称：</strong>{project_name}</p>
  <p><strong>项目编号：</strong>{project_number}</p>
  <p><strong>函件类型：</strong>{letter.type}</p>
</div>
<div style="margin:16px 0;">
{content_html}
</div>
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

    # 加载函件的额外附件
    ink_attachments = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=lid).order_by(InquiryAttachment.id)
    ).scalars().all()
    extra_attachments = []
    for att in ink_attachments:
        full_path = os.path.join(PMS_ROOT, att.filepath)
        if os.path.exists(full_path):
            with open(full_path, 'rb') as fh:
                extra_attachments.append((fh.read(), att.filename))

    try:
        from services.email_service import send_email
        send_email(
            to_addr             = sup.email,
            subject             = f"{letter.title or letter.type + '邀请函'} — {project_name}",
            body_html           = body_html,
            attachment_bytes    = buf,
            attachment_filename = attachment_filename,
            extra_attachments   = extra_attachments,
        )
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": f"邮件发送失败：{str(e)}"}), 500

    # 记录发送信息
    sup.sent_at = _now()
    sup.sent_by = session.get("display_name", "")
    db.session.commit()

    # 如果所有供应商都已发送，将函件状态更新为「进行中」
    all_suppliers = db.session.execute(
        db.select(InquirySupplier).filter_by(inquiry_id=lid)
    ).scalars().all()
    if all_suppliers and all(s.sent_at for s in all_suppliers):
        if letter.status == "草稿":
            letter.status     = "进行中"
            letter.updated_at = _now()
            db.session.commit()

    return jsonify({
        "ok": True,
        "message": f"邮件已成功发送至 {sup.email}",
        "data": sup.to_dict(),
    })


# ─────────────────────────────────────────────────────────────────
# 附件管理
# ─────────────────────────────────────────────────────────────────

@bp.route("/api/inquiries/<int:lid>/attachments", methods=["GET"])
@login_required
def list_inquiry_attachments(lid):
    atts = db.session.execute(
        db.select(InquiryAttachment).filter_by(inquiry_id=lid).order_by(InquiryAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [a.to_dict() for a in atts]})


@bp.route("/api/inquiries/<int:lid>/attachments", methods=["POST"])
@login_required
def upload_inquiry_attachment(lid):
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "函件不存在"}), 404

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    f = request.files["file"]
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
    f = request.files["file"]
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
    letter = db.session.get(InquiryLetter, lid)
    if not letter:
        return jsonify({"ok": False, "error": "函件不存在"}), 404
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
