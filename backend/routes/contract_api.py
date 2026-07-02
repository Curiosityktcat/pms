import mimetypes
import os
import threading
import uuid
from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.contract import Contract
from models.contract_attachment import ContractAttachment
from models.project import Project
from routes.utils import login_required

# ── rd-web 合同审签单直连提交状态（按合同 id 隔离）────────────────
_rdweb: dict = {}   # {cid: {running, ok, serial_no, msg}}
_rdweb_lock = threading.Lock()

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

def _can_confirm() -> bool:
    """确认合同（草案→合同上传）/撤回仅限采购人方；代理机构只能上传合同草案。"""
    return session.get("role", "") in ("officer", "assistant", "leader")

def _enrich(c: Contract):
    d = c.to_dict()
    p = db.session.get(Project, c.project_id)
    d["project_number"] = p.number if p else ""
    d["project_name"] = p.name if p else ""
    d["project_amount"] = p.amount if p else None
    d["project_category"] = p.category if p else ""
    return d

def _award_notice_uploaded(project_id, round_number) -> bool:
    """该项目该轮是否已上传中标通知书（kind='award_notice'）。"""
    from models.procurement_doc_attachment import ProcurementDocAttachment
    return db.session.execute(
        db.select(ProcurementDocAttachment.id).filter_by(
            project_id=project_id, kind="award_notice", round_number=round_number or 1
        )
    ).first() is not None


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

    # 闸门：该包须已中标方可签合同（有包记录时校验；无包记录的旧数据放行）
    from models.package import Package
    try:
        pkg_no_int = int(package_no)
    except (TypeError, ValueError):
        pkg_no_int = None
    if pkg_no_int is not None:
        pkg = db.session.execute(
            db.select(Package).filter_by(project_id=project_id, package_no=pkg_no_int)
        ).scalar_one_or_none()
        if pkg and pkg.status == "进行中":
            return jsonify({"ok": False, "error": f"包{package_no}尚未中标，无法签订合同"}), 400
        # 闸门：中标包须先上传中标通知书方可签合同（无包记录的旧数据放行）
        if pkg and pkg.status == "已中标" and not _award_notice_uploaded(project_id, pkg.won_round or 1):
            return jsonify({"ok": False, "error": f"包{package_no}尚未上传中标通知书，请先在「9. 采购结果确认」上传中标通知书后再签订合同"}), 400

    # 合同编码规则：单包 = 项目编号-HT；多包 = 项目编号-包N-HT（采购部约定）
    _pkg_total = db.session.scalar(
        db.select(db.func.count()).select_from(Package).where(Package.project_id == project_id)) or 0
    _auto_num = (f"{project.number}-HT" if _pkg_total <= 1
                 else f"{project.number}-包{package_no}-HT")
    contract_number = data.get("contract_number") or _auto_num
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


@bp.route("/<int:cid>/file/preview", methods=["GET"])
@login_required
def preview_file(cid):
    """内联预览盖章合同文件（点合同名调用，PDF/图片浏览器直接渲染）。"""
    c = db.session.get(Contract, cid)
    if not c or not c.file_saved_name:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    path = os.path.join(_file_dir(cid), c.file_saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    mime = mimetypes.guess_type(c.file_name)[0] or "application/octet-stream"
    return send_file(path, mimetype=mime, as_attachment=False, download_name=c.file_name)


@bp.route("/<int:cid>/submit", methods=["POST"])
@login_required
def submit_contract(cid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可确认合同"}), 403
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    # 多步状态机：合同草案 →(经办人提交/审核)→ 审核完成 →(上传盖章合同/完成)→ 合同上传(归档)
    if c.status == "合同草案":
        c.status = "审核完成"
        msg = "已提交，合同草案 → 审核完成"
    elif c.status == "审核完成":
        c.status = "合同上传"
        msg = "盖章合同已上传，已完成归档"
    else:
        return jsonify({"ok": False, "error": "当前状态不可提交"}), 400
    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": msg})


@bp.route("/<int:cid>/revoke", methods=["POST"])
@login_required
def revoke_contract(cid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可撤回合同"}), 403
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "不存在"}), 404
    # 逆向回退一步：合同上传 → 审核完成 → 合同草案
    if c.status == "合同上传":
        c.status = "审核完成"
        msg = "已撤回：合同上传 → 审核完成"
    elif c.status == "审核完成":
        c.status = "合同草案"
        msg = "已撤回：审核完成 → 合同草案"
    else:
        return jsonify({"ok": False, "error": "当前状态不可撤回"}), 400
    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    db.session.commit()
    return jsonify({"ok": True, "message": msg})


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


# ══════════════════════════════════════════════════════════════════
# rd-web 合同审签单直连提交
# ══════════════════════════════════════════════════════════════════

@bp.route("/<int:cid>/submit-to-rdweb", methods=["POST"])
@login_required
def submit_to_rdweb(cid):
    """从 PMS 合同数据自动提交到 rd-web 合同审签单。"""
    c = db.session.get(Contract, cid)
    if not c:
        return jsonify({"ok": False, "error": "合同不存在"}), 404
    project = db.session.get(Project, c.project_id)

    with _rdweb_lock:
        if _rdweb.get(cid, {}).get("running"):
            return jsonify({"ok": False, "error": "该合同正在提交 rd-web，请稍后重试"}), 429
        _rdweb[cid] = {"running": True, "ok": None, "serial_no": "", "msg": "提交中…"}

    from routes.utils import get_rdweb_creds
    _rdweb_user, _rdweb_pass = get_rdweb_creds(session.get("display_name", ""))

    # 构造 rd-web 表单数据（前端可通过请求体覆盖任意字段）
    if c.amount_is_text:
        amount_str = c.amount_text or ""
    else:
        amount_str = f"¥{c.amount:,.2f}" if c.amount is not None else ""

    pkg_label = f"{c.contract_name}　包{c.package_no or '1'}"

    rdweb_data = {
        "合同名称":       c.contract_name or "",
        "合同编码":       c.contract_number or "",
        "项目名称及包号": pkg_label,
        "归口管理科室":   (project.manage_dept if project else "") or "",
        "合同金额":       amount_str,
        "合同甲方":       "内江市第一人民医院",
        "甲方法定代表人": "谢晓阳",
        "甲方联系电话":   "0832-2256120",
        "甲方地址":       "四川省内江市市中区沱中路41号、汉安大道西段1866号",
        "合同乙方":       c.supplier_name or "",
        "乙方法定代表人": c.supplier_legal_rep or "",
        "乙方联系电话":   c.supplier_contact or "",
        "乙方地址":       c.supplier_address or "",
        "合同类别":       "采购部合同",
        "经办人":         (project.officer if project else "") or "",
    }
    # 前端可覆盖字段值（用户核对后修改）
    body = request.get_json(silent=True) or {}
    overrides = body.get("data") or {}
    rdweb_data.update({k: v for k, v in overrides.items() if k in rdweb_data})

    # 收集所有附件（主文件 + ContractAttachment + 中标通知书，按上传顺序）
    _uploads = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))
    attachments_to_upload = []

    # 1. 合同主文件
    if c.file_saved_name:
        fp = os.path.join(_file_dir(cid), c.file_saved_name)
        if os.path.exists(fp):
            attachments_to_upload.append({"path": fp, "name": c.file_name or c.file_saved_name})

    # 2. 合同附件（ContractAttachment，按上传顺序）
    atts = db.session.execute(
        db.select(ContractAttachment)
        .filter_by(contract_id=cid)
        .order_by(ContractAttachment.id.asc())
    ).scalars().all()
    for att in atts:
        if att.saved_name:
            fp = os.path.join(_att_dir(cid), att.saved_name)
            if os.path.exists(fp):
                attachments_to_upload.append({
                    "path": fp,
                    "name": att.original_name or att.saved_name,
                })

    # 3. 中标通知书（若有，取最新一份）
    if c.project_id:
        from models.procurement_doc_attachment import ProcurementDocAttachment
        notices = db.session.execute(
            db.select(ProcurementDocAttachment)
            .filter_by(project_id=c.project_id, kind="award_notice")
            .order_by(ProcurementDocAttachment.id.desc())
        ).scalars().all()
        for notice in notices[:1]:
            if notice.saved_name:
                fp = os.path.join(_uploads, "procurement_result",
                                  str(c.project_id), notice.saved_name)
                if os.path.exists(fp):
                    attachments_to_upload.append({
                        "path": fp,
                        "name": notice.original_name or notice.saved_name,
                    })

    if not attachments_to_upload:
        with _rdweb_lock:
            _rdweb[cid] = {"running": False, "ok": False, "serial_no": "",
                           "msg": "请先上传合同附件文件，rd-web 审签单要求必须上传附件"}
        return jsonify({"ok": False,
                        "error": "请先上传合同附件文件，rd-web 审签单要求必须上传附件"}), 400

    def _worker():
        import sys, traceback
        from services.contract_submit import submit_contract as rdweb_submit
        print(f"[rdweb] 开始提交 cid={cid}, user={_rdweb_user}, attachments={len(attachments_to_upload)}", flush=True)
        try:
            res = rdweb_submit(data=rdweb_data, attachments=attachments_to_upload,
                               loginuser=_rdweb_user, password=_rdweb_pass)
            print(f"[rdweb] 提交结果 cid={cid}: ok={res.get('ok')} serial={res.get('serial_no','')} msg={res.get('msg','')[:100]}", flush=True)
            with _rdweb_lock:
                _rdweb[cid] = {
                    "running": False,
                    "ok":        res["ok"],
                    "serial_no": res.get("serial_no", ""),
                    "msg":       res.get("msg", ""),
                }
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[rdweb] 提交异常 cid={cid}: {e}\n{tb}", flush=True)
            with _rdweb_lock:
                _rdweb[cid] = {"running": False, "ok": False, "serial_no": "", "msg": str(e)[:300]}

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始提交 rd-web"})


@bp.route("/<int:cid>/rdweb-status")
@login_required
def rdweb_contract_status(cid):
    return jsonify({"ok": True, "data": _rdweb.get(cid, {
        "running": False, "ok": None, "serial_no": "", "msg": ""
    })})
