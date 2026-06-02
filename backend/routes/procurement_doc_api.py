import datetime
import hashlib
import os
import uuid
from flask import Blueprint, request, session, jsonify, send_file
from models import db
from models.project import Project
from models.agency import Agency
from models.procurement_doc_attachment import ProcurementDocAttachment
from routes.utils import login_required

bp = Blueprint("procurement_doc", __name__, url_prefix="/api/projects")

# 采购文件编制阶段上传附件的存储根目录
UPLOAD_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "uploads", "procurement_doc")
)
os.makedirs(UPLOAD_ROOT, exist_ok=True)

ALLOWED_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".png", ".jpg", ".jpeg", ".zip", ".rar",
}


def _check_project_access(project):
    """返回 (ok, error_json, status)；校验项目可用且当前用户有权操作。"""
    if not project:
        return False, {"ok": False, "error": "项目不存在"}, 404
    if project.is_draft:
        return False, {"ok": False, "error": "草稿项目无法生成采购文件"}, 400
    if not project.agency_code:
        return False, {"ok": False, "error": "该项目不走代理机构"}, 400
    role = session.get("role", "")
    if role == "officer" and project.officer != session.get("display_name", ""):
        return False, {"ok": False, "error": "无权操作该项目"}, 403
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return False, {"ok": False, "error": "无权操作该项目"}, 403
    return True, None, 200


def _agency_name(project, override=""):
    if override:
        return override.strip()
    a = db.session.execute(
        db.select(Agency).filter_by(code=project.agency_code)
    ).scalar_one_or_none()
    return a.name if a else project.agency_code


@bp.route("/<int:pid>/bid-cover", methods=["POST"])
@login_required
def generate_bid_cover(pid):
    """按模板生成招标文件封面 Word。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    from services.bid_cover_word import generate
    try:
        buf, filename = generate(
            project,
            _agency_name(project, data.get("agency_name", "")),
            compile_date=(data.get("compile_date") or "").strip(),
            round_number=int(data.get("round_number") or project.round or 1),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ── 两步确认：采购需求确认(demand) / 采购文件确认(doc) ──────────────────
_CONFIRM_FIELDS = {
    "demand": ("demand_confirmed", "demand_confirmed_by", "demand_confirmed_at"),
    "doc":    ("doc_confirmed",    "doc_confirmed_by",    "doc_confirmed_at"),
}


@bp.route("/<int:pid>/doc-confirm", methods=["POST"])
@login_required
def set_doc_confirm(pid):
    """标记/撤销 采购需求确认 或 采购文件确认（记录确认人与时间）。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    kind = data.get("kind", "")
    if kind not in _CONFIRM_FIELDS:
        return jsonify({"ok": False, "error": "确认类型无效"}), 400
    # 确认由采购人方（经办人/助理/负责人）审核，代理机构只能上传不能确认
    if session.get("role", "") == "agency":
        return jsonify({"ok": False, "error": "代理机构只能上传文件，确认由经办人审核"}), 403
    confirmed = bool(data.get("confirmed", True))

    f_flag, f_by, f_at = _CONFIRM_FIELDS[kind]
    if confirmed:
        setattr(project, f_flag, 1)
        setattr(project, f_by, session.get("display_name", ""))
        setattr(project, f_at, datetime.datetime.now().isoformat(timespec="seconds"))
    else:
        setattr(project, f_flag, 0)
        setattr(project, f_by, "")
        setattr(project, f_at, "")
    db.session.commit()
    return jsonify({"ok": True, "data": project.to_dict()})


@bp.route("/<int:pid>/content-confirm-word", methods=["POST"])
@login_required
def generate_content_confirm_word(pid):
    """生成《院内竞选文件内容确认表》Word。"""
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status

    data = request.get_json(silent=True) or {}
    # 收集该项目采购文件(doc)附件的 SHA256，填入内容确认表
    docs = db.session.execute(
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id == pid)
        .where(ProcurementDocAttachment.kind == "doc")
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()
    file_hashes = [(d.original_name, d.sha256) for d in docs if d.sha256]

    from services.content_confirm_word import generate
    try:
        buf, filename = generate(
            project,
            _agency_name(project, data.get("agency_name", "")),
            file_hashes=file_hashes,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ── 上传附件（采购需求确认 等）─────────────────────────────────────────
def _attach_dir(pid: int) -> str:
    d = os.path.join(UPLOAD_ROOT, str(pid))
    os.makedirs(d, exist_ok=True)
    return d


def _norm_kind(raw):
    return raw if raw in ("demand", "doc") else "demand"


def _kind_confirmed(project, kind):
    """该确认环节是否已确认（已确认则锁定，不允许增删文件）。"""
    flag = "doc_confirmed" if kind == "doc" else "demand_confirmed"
    return bool(getattr(project, flag, 0))


def _sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


@bp.route("/<int:pid>/doc-attachments", methods=["GET"])
@login_required
def list_doc_attachments(pid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    kind = _norm_kind(request.args.get("kind", "demand"))
    rows = db.session.execute(
        db.select(ProcurementDocAttachment)
        .where(ProcurementDocAttachment.project_id == pid)
        .where(ProcurementDocAttachment.kind == kind)
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:pid>/doc-attachments", methods=["POST"])
@login_required
def upload_doc_attachment(pid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    kind = _norm_kind(request.args.get("kind", "demand"))
    if _kind_confirmed(project, kind):
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤销确认"}), 400

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    _, ext = os.path.splitext(f.filename.lower())
    if ext not in ALLOWED_EXTS:
        return jsonify({"ok": False, "error": f"不支持的文件格式：{ext}，支持 PDF/Word/Excel/图片/压缩包"}), 400

    saved_name = f"{uuid.uuid4().hex}{ext}"
    save_path = os.path.join(_attach_dir(pid), saved_name)
    f.save(save_path)
    file_size = os.path.getsize(save_path)
    sha256 = _sha256_of(save_path)

    att = ProcurementDocAttachment(
        project_id=pid,
        kind=kind,
        original_name=f.filename,
        saved_name=saved_name,
        file_size=file_size,
        sha256=sha256,
        uploaded_by=session.get("display_name", ""),
        uploaded_at=datetime.datetime.now().isoformat(timespec="seconds"),
    )
    db.session.add(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "上传成功", "data": att.to_dict()}), 201


@bp.route("/<int:pid>/doc-attachments/<int:aid>", methods=["GET"])
@login_required
def download_doc_attachment(pid, aid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    path = os.path.join(_attach_dir(pid), att.saved_name)
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "文件已丢失，请重新上传"}), 404
    return send_file(path, as_attachment=True, download_name=att.original_name)


@bp.route("/<int:pid>/doc-attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete_doc_attachment(pid, aid):
    project = db.session.get(Project, pid)
    ok, err, status = _check_project_access(project)
    if not ok:
        return jsonify(err), status
    att = db.session.get(ProcurementDocAttachment, aid)
    if not att or att.project_id != pid:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    if _kind_confirmed(project, att.kind):
        return jsonify({"ok": False, "error": "已确认，如需修改请先撤销确认"}), 400
    try:
        path = os.path.join(_attach_dir(pid), att.saved_name)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    db.session.delete(att)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})
