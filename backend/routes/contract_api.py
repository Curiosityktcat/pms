import mimetypes
import os
import uuid
from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.contract import Contract
from models.contract_attachment import ContractAttachment
from models.project import Project
from routes.utils import login_required

bp = Blueprint("contract", __name__, url_prefix="/api/contracts")

UPLOAD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "contracts")
)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

ALLOWED_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png"}

def _file_dir(cid: int) -> str:
    d = os.path.join(UPLOAD_ROOT, str(cid))
    os.makedirs(d, exist_ok=True)
    return d

def _enrich(c: Contract):
    d = c.to_dict()
    p = db.session.get(Project, c.project_id)
    d["project_number"] = p.number if p else ""
    d["project_name"] = p.name if p else ""
    d["project_amount"] = p.amount if p else None
    d["project_category"] = p.category if p else ""
    return d

def _validate_amount(amount, project):
    """数字金额不能超过项目预算"""
    if amount is None:
        return None
    try:
        amount_f = float(amount)
    except (TypeError, ValueError):
        return "合同金额格式错误"
    if project and project.amount and amount_f > project.amount:
        return f"合同金额（¥{amount_f:,.2f}）不能超过项目预算金额（¥{project.amount:,.2f}）"
    return None


@bp.route("", methods=["GET"])
@login_required
def list_contracts():
    project_id = request.args.get("project_id", type=int)
    role = session.get("role", "")
    agency_code = session.get("agency_code", "")
    q = db.select(Contract)
    if project_id:
        q = q.where(Contract.project_id == project_id)
    rows = db.session.execute(q.order_by(Contract.id.desc())).scalars().all()
    result = []
    for c in rows:
        # agency 只看自己的项目
        if role == "agency":
            p = db.session.get(Project, c.project_id)
            if not p or p.agency_code != agency_code:
                continue
        result.append(_enrich(c))
    return jsonify({"ok": True, "data": result})


@bp.route("", methods=["POST"])
@login_required
def create_contract():
    data = request.get_json(force=True) or {}
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    project_id = data.get("project_id")
    if not project_id:
        return jsonify({"ok": False, "error": "必须指定项目"}), 400
    project = db.session.get(Project, project_id)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404

    package_no = data.get("package_no", "1") or "1"
    contract_number = data.get("contract_number") or f"{project.number}-{package_no}-HT"
    contract_name = data.get("contract_name") or project.name

    amount_is_text = int(data.get("amount_is_text", 0))
    amount = data.get("amount") if not amount_is_text else None
    if not amount_is_text and amount is not None:
        err = _validate_amount(amount, project)
        if err:
            return jsonify({"ok": False, "error": err}), 400

    c = Contract(
        project_id=project_id,
        contract_number=contract_number,
        contract_name=contract_name,
        package_no=package_no,
        status="合同草案",
        supplier_name=data.get("supplier_name", ""),
        supplier_address=data.get("supplier_address", ""),
        supplier_contact=data.get("supplier_contact", ""),
        supplier_legal_rep=data.get("supplier_legal_rep", ""),
        amount_is_text=amount_is_text,
        amount_text=data.get("amount_text", "") if amount_is_text else "",
        amount=float(amount) if amount is not None else None,
        sign_date=data.get("sign_date", ""),
        service_start=data.get("service_start", ""),
        service_end=data.get("service_end", ""),
        notes=data.get("notes", ""),
        created_by=session.get("display_name", ""),
        created_at=now,
        updated_at=now,
    )
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich(c)})


@bp.route("/<int:cid>", methods=["PUT"])
@login_required
def update_contract(cid):
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    data = request.get_json(force=True) or {}
    project = db.session.get(Project, c.project_id)

    updatable = ["contract_number","contract_name","package_no","supplier_name",
                 "supplier_address","supplier_contact","supplier_legal_rep",
                 "amount_is_text","amount_text","amount","sign_date",
                 "service_start","service_end","notes"]
    for k in updatable:
        if k in data:
            setattr(c, k, data[k])

    # 金额验证
    if not c.amount_is_text and c.amount is not None:
        err = _validate_amount(c.amount, project)
        if err:
            return jsonify({"ok": False, "error": err}), 400

    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "data": _enrich(c)})


@bp.route("/<int:cid>", methods=["DELETE"])
@login_required
def delete_contract(cid):
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    # 删除文件
    if c.file_saved_name:
        path = os.path.join(_file_dir(cid), c.file_saved_name)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(c)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<int:cid>/upload", methods=["POST"])
@login_required
def upload_file(cid):
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"不支持的格式：{ext}"}), 400
    saved_name = uuid.uuid4().hex + ext
    f.save(os.path.join(_file_dir(cid), saved_name))
    # 删除旧文件
    if c.file_saved_name and c.file_saved_name != saved_name:
        old = os.path.join(_file_dir(cid), c.file_saved_name)
        if os.path.exists(old):
            os.remove(old)
    c.file_name = f.filename
    c.file_saved_name = saved_name
    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "file_name": f.filename})


@bp.route("/<int:cid>/file", methods=["GET"])
@login_required
def download_file(cid):
    c = db.session.get(Contract, cid)
    if not c or not c.file_saved_name:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    path = os.path.join(_file_dir(cid), c.file_saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(path, as_attachment=True, download_name=c.file_name)


@bp.route("/<int:cid>/submit", methods=["POST"])
@login_required
def submit_contract(cid):
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    # 签订时间由前端在合同上传阶段单独保存，这里不再强制校验
    c.status = "合同上传"
    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": "已提交为合同上传"})


@bp.route("/<int:cid>/revoke", methods=["POST"])
@login_required
def revoke_contract(cid):
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    c.status = "合同草案"
    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回为合同草案"})


# ══════════════════════════════════════════════════════════════════
# 合同附件接口
# ══════════════════════════════════════════════════════════════════

def _att_dir(cid: int) -> str:
    d = os.path.join(UPLOAD_ROOT, str(cid), "attachments")
    os.makedirs(d, exist_ok=True)
    return d

PREVIEW_MIME = {
    ".pdf":  "application/pdf",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".gif":  "image/gif",
    ".webp": "image/webp",
}


@bp.route("/<int:cid>/attachments", methods=["GET"])
@login_required
def list_attachments(cid):
    rows = db.session.execute(
        db.select(ContractAttachment)
        .where(ContractAttachment.contract_id == cid)
        .order_by(ContractAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:cid>/attachments", methods=["POST"])
@login_required
def upload_attachment(cid):
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "合同不存在"}), 404
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"不支持的格式：{ext}"}), 400

    saved_name = uuid.uuid4().hex + ext
    save_path = os.path.join(_att_dir(cid), saved_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    mime = PREVIEW_MIME.get(ext) or mimetypes.guess_type(f.filename)[0] or "application/octet-stream"
    stage = request.form.get("stage", "草案")
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    att = ContractAttachment(
        contract_id=cid,
        original_name=f.filename,
        saved_name=saved_name,
        file_size=file_size,
        mime_type=mime,
        stage=stage,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=now,
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "data": att.to_dict()})


@bp.route("/<int:cid>/attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete_attachment(cid, aid):
    att = db.session.get(ContractAttachment, aid)
    if not att or att.contract_id != cid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_att_dir(cid), att.saved_name)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/<int:cid>/attachments/<int:aid>/download", methods=["GET"])
@login_required
def download_attachment(cid, aid):
    att = db.session.get(ContractAttachment, aid)
    if not att or att.contract_id != cid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_att_dir(cid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


@bp.route("/<int:cid>/attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview_attachment(cid, aid):
    """内联预览（PDF/图片直接在浏览器渲染）"""
    att = db.session.get(ContractAttachment, aid)
    if not att or att.contract_id != cid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_att_dir(cid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    mime = att.mime_type or "application/octet-stream"
    return send_file(path, mimetype=mime, as_attachment=False,
                     download_name=att.original_name)
