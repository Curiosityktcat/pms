import json
import mimetypes
import os
import threading
import time
import uuid
from datetime import datetime
from flask import Blueprint, request, session, jsonify, send_file, current_app
from models import db
from models.contract import Contract
from models.contract_attachment import ContractAttachment
from models.project import Project
from services import approval_log as alog
from routes.utils import login_required, can_view_project
from services import upload_relay
from services.dept_scope import assert_can_view_project, scope_by_project

# ── rd-web 合同审签单直连提交状态（按合同 id 隔离）────────────────
_rdweb: dict = {}   # {cid: {running, ok, serial_no, msg, started_at}}
RDWEB_STALE_SEC = 8 * 60   # 超过此时长仍未返回，认定线程僵死，允许重推

# rd-web 合同审签单上带 * 的必填文本字段（与 contract_submit.TEXT_FIELDS 同源）。
# 少一个，rd-web 自己的校验就会拦下提交且不给明确提示，
# 所以 PMS 这边在启动浏览器之前先自查一遍。
RDWEB_REQUIRED = [
    "合同名称", "合同编码", "项目名称及包号", "归口管理科室", "合同金额",
    "合同甲方", "甲方法定代表人", "甲方联系电话", "甲方地址",
    "合同乙方", "乙方法定代表人", "乙方联系电话", "乙方地址",
    "经办人",
]
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


def _scoped(cid):
    """取合同并做归属校验（agency 本机构 / officer 本人经办 / 助理·负责人·管理员全部）。
    返回 (contract, project, error)；error 非空时应直接 return error。"""
    c = db.session.get(Contract, cid)
    if not c:
        return None, None, (jsonify({"ok": False, "error": "不存在"}), 404)
    if session.get("role") in ("dept", "dept_manage", "dept_demand"):
        assert_can_view_project(c.project_id)
    project = db.session.get(Project, c.project_id)
    if not can_view_project(project):
        return None, None, (jsonify({"ok": False, "error": "无权访问该合同"}), 403)
    return c, project, None

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
    q = scope_by_project(db.select(Contract), Contract)
    if project_id:
        q = q.where(Contract.project_id == project_id)
    rows = db.session.execute(q.order_by(Contract.id.desc())).scalars().all()
    # 隔离：agency 本机构、officer 本人经办、助理/负责人/管理员全部
    result = []
    for c in rows:
        if session.get("role") not in ("dept", "dept_manage", "dept_demand") and not can_view_project(db.session.get(Project, c.project_id)):
            continue
        result.append(_enrich(c))
    from services.pending_owner import attach_pending
    attach_pending(result, "project_id")      # 每行带上当前处理人
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
    if not can_view_project(project):
        return jsonify({"ok": False, "error": "无权为该项目创建合同"}), 403

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
    c, project, err = _scoped(cid)
    if err:
        return err
    data = request.get_json(force=True) or {}

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
    c, _project, err = _scoped(cid)
    if err:
        return err
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
    c, _project, err = _scoped(cid)
    if err:
        return err
    # 同附件口：公网大文件走 OSS 中转
    f = request.files.get("file") or upload_relay.staged_file()
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
    c, _project, err = _scoped(cid)
    if err:
        return err
    if not c.file_saved_name:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    path = os.path.join(_file_dir(cid), c.file_saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    return send_file(path, as_attachment=True, download_name=c.file_name)


@bp.route("/<int:cid>/file/preview", methods=["GET"])
@login_required
def preview_file(cid):
    """内联预览盖章合同文件（点合同名调用，PDF/图片浏览器直接渲染）。"""
    c, _project, err = _scoped(cid)
    if err:
        return err
    if not c.file_saved_name:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    path = os.path.join(_file_dir(cid), c.file_saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    from services.office_convert import send_preview
    return send_preview(path, c.file_name)


def _auto_push_contract_rdweb(c):
    """合同审核完成 → 自动推 rd-web 合同审签单盖章（手绘计划⑤）。

    已经推成功过（有流水号）的不重复推；推不动也不影响合同状态流转，
    页面上还有「推送 rd-web」按钮兜底。
    """
    try:
        if (c.rdweb_serial_no or ""):
            return {}
        from routes.rdweb_approval_api import auto_push_enabled
        if not auto_push_enabled():
            return {"auto": False, "reason": "自动推送已关闭"}
        resp = submit_to_rdweb(c.id)
        body = resp[0] if isinstance(resp, tuple) else resp
        payload = body.get_json(silent=True) or {}
        if payload.get("ok") is False:
            return {"auto": True, "ok": False, "kind": "contract",
                    "msg": payload.get("error", "推送未启动")}
        return {"auto": True, "ok": True, "kind": "contract",
                "msg": "已开始自动推送合同到 rd-web 审签"}
    except Exception as e:      # noqa: BLE001
        return {"auto": True, "ok": False, "kind": "contract",
                "msg": f"自动推送未启动：{e}"[:200]}


@bp.route("/<int:cid>/submit", methods=["POST"])
@login_required
def submit_contract(cid):
    c, _project, err = _scoped(cid)
    if err:
        return err
    is_agency = session.get("role", "") == "agency"
    # 多步状态机：合同草案 →(代理机构拟好提交)→ 审核完成 →(经办人核完/传盖章件)→ 合同上传(归档)
    #
    # 第一步允许代理机构做——合同本来就是代理拟的，让经办人替他点提交没有道理；
    # 第二步（定稿归档）仍只限采购人方。
    if c.status == "合同草案":
        if not (is_agency or _can_confirm()):
            return jsonify({"ok": False, "error": "无权提交该合同"}), 403
        c.status = "审核完成"
        msg = "已提交，转经办人审核"
    elif c.status == "审核完成":
        if not _can_confirm():
            return jsonify({"ok": False, "error": "仅项目经办人或负责人可完成合同归档"}), 403
        c.status = "合同上传"
        msg = "盖章合同已上传，已完成归档"
    else:
        return jsonify({"ok": False, "error": "当前状态不可提交"}), 400
    c.updated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    alog.log(c.project_id, "contract",
             "resubmit" if c.reject_reason else "submit", target_id=c.id)
    db.session.commit()
    # 审核完成这一步是「合同定稿待盖章」，正是该去 rd-web 走审签的时点
    push_info = _auto_push_contract_rdweb(c) if c.status == "审核完成" else {}
    return jsonify({"ok": True, "message": msg, "rdweb_push": push_info})


# ── 驳回合同（打回修改，写明原因）──────────────────────────────────
@bp.route("/<int:cid>/reject", methods=["POST"])
@login_required
def reject_contract(cid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可驳回合同"}), 403
    c, _project, err = _scoped(cid)
    if err:
        return err
    if c.status == "合同草案":
        return jsonify({"ok": False, "error": "合同尚在草案阶段，无需驳回"}), 400
    reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not reason:
        return jsonify({"ok": False, "error": "请填写驳回原因"}), 400
    # 驳回一律退回「合同草案」，由编制方改完重新提交
    c.status = "合同草案"
    c.reject_reason = reason
    c.reject_count = int(c.reject_count or 0) + 1
    c.rejected_by = session.get("display_name", "")
    c.rejected_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    c.updated_at = c.rejected_at
    alog.log(c.project_id, "contract", "reject", target_id=c.id, reason=reason)
    db.session.commit()
    return jsonify({"ok": True,
                    "message": f"已驳回（第{c.reject_count}次），退回合同草案待修改"})


@bp.route("/<int:cid>/revoke", methods=["POST"])
@login_required
def revoke_contract(cid):
    if not _can_confirm():
        return jsonify({"ok": False, "error": "仅项目经办人或负责人可撤回合同"}), 403
    c, _project, err = _scoped(cid)
    if err:
        return err
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
    _c, _project, err = _scoped(cid)
    if err:
        return err
    rows = db.session.execute(
        db.select(ContractAttachment)
        .where(ContractAttachment.contract_id == cid)
        .order_by(ContractAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:cid>/attachments", methods=["POST"])
@login_required
def upload_attachment(cid):
    c, _project, err = _scoped(cid)
    if err:
        return err
    # 公网大文件走 OSS 中转（浏览器直传 OSS，这里把它拉回本地），局域网仍是普通 multipart
    f = request.files.get("file") or upload_relay.staged_file()
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
    _c, _project, err = _scoped(cid)
    if err:
        return err
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
    _c, _project, err = _scoped(cid)
    if err:
        return err
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
    _c, _project, err = _scoped(cid)
    if err:
        return err
    att = db.session.get(ContractAttachment, aid)
    if not att or att.contract_id != cid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_att_dir(cid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失"}), 404
    from services.office_convert import send_preview
    return send_preview(path, att.original_name, mimetype=att.mime_type)


# ══════════════════════════════════════════════════════════════════
# rd-web 合同审签单直连提交
# ══════════════════════════════════════════════════════════════════

@bp.route("/<int:cid>/submit-to-rdweb", methods=["POST"])
@login_required
def submit_to_rdweb(cid):
    """从 PMS 合同数据自动提交到 rd-web 合同审签单。"""
    c, project, err = _scoped(cid)
    if err:
        return err
    app = current_app._get_current_object()

    with _rdweb_lock:
        # 同 rdweb_contract_api：线程僵死会让这个合同永远推不了，超时后强制接管
        st = _rdweb.get(cid, {})
        started = st.get("started_at", 0)
        stale = st.get("running") and started and (time.time() - started > RDWEB_STALE_SEC)
        if st.get("running") and not stale:
            waited = int(time.time() - started) if started else 0
            return jsonify({"ok": False,
                            "error": f"该合同正在提交 rd-web（已 {waited} 秒），请稍后重试"}), 429
        if stale:
            print(f"[rdweb] 合同 {cid} 上次提交已僵死，自动解锁重来", flush=True)
        _rdweb[cid] = {"running": True, "ok": None, "serial_no": "", "msg": "提交中…",
                       "started_at": time.time()}

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

    # ── 推送前先自查必填字段 ──────────────────────────────────────
    # rd-web 那 13 个文本字段全部带 * 必填，缺一个就会在点「提交」后
    # 卡住不关表单，报「可能存在校验错误」——而那时浏览器自动化已经跑了两分钟。
    # 与其事后猜，不如出发前就说清楚缺哪个，让人几秒钟补上。
    missing = [k for k in RDWEB_REQUIRED if not str(rdweb_data.get(k, "")).strip()]
    if missing:
        tip = "、".join(missing)
        with _rdweb_lock:
            _rdweb[cid] = {"running": False, "ok": False, "serial_no": "",
                           "msg": f"合同信息不全，缺：{tip}"}
        return jsonify({
            "ok": False,
            "error": f"以下 rd-web 必填项为空，请先在合同里补全再推送：{tip}",
            "missing": missing,
        }), 400

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

    # 合同名称 = 附件里的真实合同名称 + 项目名称（原来只有项目名称，审签单上
    # 看不出这是什么合同）。用户在前端显式改过合同名称的，尊重用户填的。
    if "合同名称" not in overrides:
        from services.rdweb_contract_name import compose as _compose_cname
        _cname = _compose_cname(c.contract_name or "",
                                (project.name if project else "") or "",
                                attachments_to_upload)
        if _cname:
            rdweb_data["合同名称"] = _cname

    # 落一条推送记录：之前从合同管理推的失败不写库，排查只能翻系统日志
    from models.rdweb_push_log import RdwebPushLog
    _log = RdwebPushLog(
        username=session.get("user", ""),
        display_name=session.get("display_name", ""),
        contract_name=c.contract_name or "",
        file_name="、".join(a["name"] for a in attachments_to_upload)[:200],
        data_json=json.dumps(rdweb_data, ensure_ascii=False),
        status="running",
    )
    db.session.add(_log)
    db.session.commit()
    _log_id = _log.id

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
            with app.app_context():
                _row = db.session.get(RdwebPushLog, _log_id)
                if _row is not None:
                    _row.status = "ok" if res.get("ok") else "fail"
                    _row.serial_no = res.get("serial_no", "")
                    _row.msg = (res.get("msg", "") or "")[:500]
                    _row.finished_at = datetime.now()
                    db.session.commit()
            # 成功且有流水号 → 落库到合同，供项目列表打标
            if res.get("ok") and res.get("serial_no"):
                try:
                    with app.app_context():
                        _c = db.session.get(Contract, cid)
                        if _c:
                            _c.rdweb_serial_no = res.get("serial_no", "")
                            _c.rdweb_submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            db.session.commit()
                except Exception as _pe:
                    print(f"[rdweb] 合同流水号落库失败 cid={cid}: {_pe}", flush=True)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[rdweb] 提交异常 cid={cid}: {e}\n{tb}", flush=True)
            with _rdweb_lock:
                _rdweb[cid] = {"running": False, "ok": False, "serial_no": "", "msg": str(e)[:300]}
            try:
                with app.app_context():
                    _row = db.session.get(RdwebPushLog, _log_id)
                    if _row is not None:
                        _row.status = "fail"
                        _row.msg = str(e)[:500]
                        _row.finished_at = datetime.now()
                        db.session.commit()
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始提交 rd-web"})


@bp.route("/<int:cid>/rdweb-status")
@login_required
def rdweb_contract_status(cid):
    _c, _project, err = _scoped(cid)
    if err:
        return err
    return jsonify({"ok": True, "data": _rdweb.get(cid, {
        "running": False, "ok": None, "serial_no": "", "msg": ""
    })})


@bp.route("/<int:cid>/rdweb-autofill", methods=["POST"])
@login_required
def rdweb_contract_autofill(cid):
    """读取合同附件内容，AI 抽取 rd-web 审签字段（与工具页同一套逻辑）。

    识别源优先级：合同主文件 → 第一个合同附件（跳过读不出字的继续试下一个）。"""
    from services.rdweb_autofill import extract_file_text, autofill_fields, FIELD_KEYS

    c, _project, err = _scoped(cid)
    if err:
        return err

    candidates = []
    if c.file_saved_name:
        fp = os.path.join(_file_dir(cid), c.file_saved_name)
        if os.path.exists(fp):
            candidates.append((fp, c.file_name or c.file_saved_name))
    atts = db.session.execute(
        db.select(ContractAttachment)
        .filter_by(contract_id=cid)
        .order_by(ContractAttachment.id.asc())
    ).scalars().all()
    for att in atts:
        if att.saved_name:
            fp = os.path.join(_att_dir(cid), att.saved_name)
            if os.path.exists(fp):
                candidates.append((fp, att.original_name or att.saved_name))
    if not candidates:
        return jsonify({"ok": False, "error": "该合同还没有附件，请先上传合同文件"}), 400

    text, src_name, last_err = "", "", ""
    for fp, name in candidates:
        try:
            text = extract_file_text(fp)
            src_name = name
            break
        except RuntimeError as e:
            last_err = str(e)
    if not text:
        return jsonify({"ok": False, "error": f"附件内容识别失败：{last_err}"}), 422

    usage_ctx = {"username": session.get("user", ""),
                 "display_name": session.get("display_name", ""),
                 "feature": "合同审签推送-自动填写(合同管理)"}
    try:
        out = autofill_fields(text, usage_ctx=usage_ctx,
                              operator=session.get("display_name", ""))
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    filled = sum(1 for k in FIELD_KEYS if out.get(k))
    return jsonify({"ok": True, "data": out, "filled": filled, "source": src_name})
