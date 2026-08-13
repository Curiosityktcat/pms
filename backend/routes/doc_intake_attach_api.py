"""资料智能归档 → PMS 自动挂载  /api/doc-intake

doc-intake 识别归档后，把文件按「档案类型 + 项目编号」自动挂到 PMS 的对应位置，
省掉「归档一次、再到业务模块手动上传一次」的重复动作。

设计上只做加法，绝不覆盖：
    盖章合同槽位空着才自动填进去；已经有文件了就作为合同附件追加，
    并在返回里说明去向。识别错了顶多多一个附件，不会把已有的正式件冲掉。

调用方是内网容器，用共享密钥认证（不走用户会话）。密钥文件与牛马反代同一套路。
"""
import datetime
import hashlib
import hmac
import os
import uuid

from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename

from models import db
from models.project import Project
from models.contract import Contract
from models.contract_attachment import ContractAttachment
from models.procurement_doc_attachment import ProcurementDocAttachment

bp = Blueprint("doc_intake_attach", __name__, url_prefix="/api/doc-intake")

_PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_UPLOADS = os.path.abspath(os.path.join(_PMS_ROOT, "..", "uploads"))

# 档案类型 → 挂载去向。
#   kind=...      挂到 ProcurementDocAttachment 的对应 kind（走 uploads/<subdir>/<pid>/）
#   contract=True 挂到该项目的合同（盖章件或合同附件）
ROUTING = {
    "采购合同":         {"contract": True},
    "中标成交通知书":   {"kind": "award_notice", "subdir": "procurement_result"},
    "成交结果确认函":   {"kind": "result",       "subdir": "procurement_result"},
    "招标采购文件":     {"kind": "doc",          "subdir": "procurement_doc"},
    "采购需求":         {"kind": "demand",       "subdir": "procurement_doc"},
    "评标评审报告":     {"kind": "review_result", "subdir": "project_review"},
    "资格审查":         {"kind": "review_result", "subdir": "project_review"},
    "开标记录":         {"kind": "review_result", "subdir": "project_review"},
    "询价报价单":       {"kind": "result",       "subdir": "procurement_result"},
}

ALLOWED_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx",
                ".png", ".jpg", ".jpeg", ".zip", ".rar"}


def _secret() -> str:
    p = os.environ.get("INTAKE_ATTACH_SECRET_FILE",
                       "/home/huangxb/pms/.intake_attach_secret")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return os.environ.get("INTAKE_ATTACH_SECRET", "")


def _auth_ok() -> bool:
    want = _secret()
    if not want:          # 没配密钥 = 功能未启用，一律拒绝，避免裸奔
        return False
    got = request.headers.get("X-Intake-Secret", "")
    return hmac.compare_digest(got, want)


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _safe_name(name: str) -> str:
    """保留中文文件名，只剥路径与危险字符。"""
    name = os.path.basename(name or "").replace("\x00", "").strip()
    if name in ("", ".", ".."):
        name = secure_filename(name) or "file"
    return name[:180]


def _save(fileobj, subdir: str, pid: int):
    d = os.path.join(_UPLOADS, subdir, str(pid))
    os.makedirs(d, exist_ok=True)
    orig = _safe_name(fileobj.filename)
    ext = os.path.splitext(orig)[1].lower()
    saved = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(d, saved)
    fileobj.save(path)
    size = os.path.getsize(path)
    sha = hashlib.sha256(open(path, "rb").read()).hexdigest() if size < 60 * 1024 * 1024 else ""
    return orig, saved, path, size, sha


def _current_round(pid: int) -> int:
    try:
        from services.project_progress import stage_map
        return (stage_map([pid]).get(pid, {}) or {}).get("current_round") or 1
    except Exception:
        return 1


@bp.route("/attach", methods=["POST"])
def attach():
    """把一份已识别归档的资料挂到 PMS 对应位置。

    form: file（必填）、doc_type、project_no、uploaded_by、summary
    """
    if not _auth_ok():
        return jsonify({"ok": False, "error": "未授权"}), 403

    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"ok": False, "error": "没有收到文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False, "error": f"不支持的文件类型 {ext}"}), 400

    doc_type = (request.form.get("doc_type") or "").strip()
    project_no = (request.form.get("project_no") or "").strip()
    uploaded_by = (request.form.get("uploaded_by") or "资料智能归档").strip()

    if not project_no:
        return jsonify({"ok": False, "attached": False,
                        "reason": "没有识别出项目编号，未挂载"}), 200

    project = db.session.execute(
        db.select(Project).filter_by(number=project_no)).scalar_one_or_none()
    if project is None:
        return jsonify({"ok": False, "attached": False,
                        "reason": f"PMS 里没有编号为 {project_no} 的项目，未挂载"}), 200

    route = ROUTING.get(doc_type)
    if not route:
        return jsonify({"ok": True, "attached": False,
                        "reason": f"「{doc_type}」没有对应的挂载位置，仍留在归档库"}), 200

    # ── 合同：优先补盖章件槽位，已有则追加为合同附件（只做加法，不覆盖）──
    if route.get("contract"):
        c = db.session.execute(
            db.select(Contract).filter_by(project_id=project.id)
            .order_by(Contract.id.desc())).scalars().first()
        if c is None:
            return jsonify({"ok": True, "attached": False,
                            "reason": "该项目还没有合同记录，无法挂载盖章合同"}), 200
        orig, saved, path, size, _sha = _save(f, "contracts", c.id)
        if not c.file_saved_name:
            c.file_name = orig
            c.file_saved_name = saved
            c.updated_at = _now()
            db.session.commit()
            where = f"合同管理 → {c.contract_name or '合同'} → 盖章合同"
        else:
            db.session.add(ContractAttachment(
                contract_id=c.id, original_name=orig, saved_name=saved,
                file_size=size, stage="合同上传", uploaded_by=uploaded_by,
                uploaded_at=_now()))
            db.session.commit()
            where = f"合同管理 → {c.contract_name or '合同'} → 合同附件（盖章件槽位已有文件，未覆盖）"
        return jsonify({"ok": True, "attached": True, "where": where,
                        "project": project.number, "contract_id": c.id})

    # ── 其余：挂到 ProcurementDocAttachment 的对应 kind ────────────
    kind, subdir = route["kind"], route["subdir"]
    orig, saved, path, size, sha = _save(f, subdir, project.id)
    rnd = _current_round(project.id)
    db.session.add(ProcurementDocAttachment(
        project_id=project.id, kind=kind, original_name=orig, saved_name=saved,
        file_size=size, sha256=sha, round_number=rnd,
        uploaded_by=uploaded_by, uploaded_at=_now()))
    db.session.commit()
    label = {
        "award_notice": "采购结果确认 → 中标通知书",
        "result": "采购结果确认 → 单价/报价附件",
        "doc": "采购文件确认（5.2）→ 采购文件",
        "demand": "采购需求确认（5.1）→ 需求资料",
        "review_result": "项目评审资料上传（8.5）",
    }.get(kind, kind)
    return jsonify({"ok": True, "attached": True,
                    "where": f"{label}（第{rnd}次采购）",
                    "project": project.number, "kind": kind})


@bp.route("/routing", methods=["GET"])
def routing():
    """可挂载的档案类型与去向，供前端说明与排错。"""
    return jsonify({"ok": True, "data": {
        k: ("合同管理·盖章合同" if v.get("contract") else v.get("kind"))
        for k, v in ROUTING.items()
    }})
