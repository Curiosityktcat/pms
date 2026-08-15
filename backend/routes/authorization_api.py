"""人员授权台账与凭证接口。"""
import json
import os
import time
from datetime import datetime

from flask import Blueprint, jsonify, request, send_file, session
from werkzeug.utils import secure_filename

from models import db
from models.authorization import Authorization
from models.dept import Dept
from models.user import User
from models.user_audit_log import UserAuditLog
from routes.utils import login_required
from services.authorization import effective_state, parse_perm_keys
from services.permission import ALL_PERM_KEYS, PERMISSION_CATALOG, get_user_perms, is_admin_user

bp = Blueprint("authorization", __name__, url_prefix="/api/authorizations")

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads", "authorizations"))
_MAX_FILE_SIZE = 20 * 1024 * 1024
_SOURCES = {"resolution", "delegate"}


def _error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def _can_manage():
    return is_admin_user(session.get("user", "")) or session.get("role") in ("assistant", "dept", "dept_manage", "dept_demand")


def _full_hospital():
    return is_admin_user(session.get("user", "")) or session.get("role") == "assistant"


def _manage_required(func):
    """管理接口统一拦截，避免只靠前端隐藏菜单造成越权。"""
    from functools import wraps

    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
        if not _can_manage() or "authz_manage" not in get_user_perms(session["user"], session["role"]):
            return _error("无权限", 403)
        return func(*args, **kwargs)
    return wrapper


def _safe_name(name):
    name = os.path.basename(name or "").replace("\x00", "").strip()
    if name in ("", ".", ".."):
        name = secure_filename(name) or "authorization.pdf"
    return name


def _inside_upload_root(path):
    try:
        return os.path.commonpath((_ROOT, os.path.abspath(path))) == _ROOT
    except (TypeError, ValueError):
        return False


def _row_dict(row, dept_heads=None):
    heads = dept_heads or {}
    return {
        "id": row.id,
        "grantee_username": row.grantee_username,
        "grantee_name": row.grantee_name,
        "grantee_dept_code": row.grantee_dept_code,
        "source": row.source,
        "granter_name": row.granter_name,
        "granter_dept_code": row.granter_dept_code,
        "granter_head_snapshot": row.granter_head_snapshot,
        "doc_no": row.doc_no or "",
        "perm_keys": parse_perm_keys(row.perm_keys),
        "valid_from": row.valid_from,
        "valid_to": row.valid_to,
        "doc_name": row.doc_name,
        "status": row.status,
        "effective_state": effective_state(row, heads.get(row.granter_dept_code, "")),
        "created_by": row.created_by,
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
        "revoked_by": row.revoked_by or "",
        "revoked_at": row.revoked_at.strftime("%Y-%m-%d %H:%M:%S") if row.revoked_at else "",
        "revoke_reason": row.revoke_reason or "",
    }


def _heads(rows):
    codes = {row.granter_dept_code for row in rows if row.source == "delegate"}
    return dict(db.session.execute(
        db.select(Dept.code, Dept.head_name).where(Dept.code.in_(codes))
    ).all()) if codes else {}


def _parse_date(value, label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{label}必须是 YYYY-MM-DD 格式")


def _audit(action, auth, detail):
    # 复用账号审计表：target_username 指向被授权账号，detail 保留授权记录 id 和变化原因。
    db.session.add(UserAuditLog(
        actor=session.get("user", ""), actor_name=session.get("display_name", ""),
        action=action, target_id=auth.id, target_username=auth.grantee_username,
        detail=json.dumps(detail, ensure_ascii=False),
    ))


@bp.route("", methods=["GET"])
@_manage_required
def list_authorizations():
    stmt = db.select(Authorization)
    if session.get("role") in ("dept", "dept_manage", "dept_demand"):
        stmt = stmt.where(Authorization.grantee_dept_code == session.get("dept_code", ""))
    dept_code = (request.args.get("dept_code") or "").strip().upper()
    grantee = (request.args.get("grantee") or "").strip()
    source = (request.args.get("source") or "").strip()
    state = (request.args.get("status") or "").strip()
    if dept_code and _full_hospital():
        stmt = stmt.where(Authorization.grantee_dept_code == dept_code)
    if grantee:
        like = f"%{grantee}%"
        stmt = stmt.where(db.or_(Authorization.grantee_username.like(like), Authorization.grantee_name.like(like)))
    if source in _SOURCES:
        stmt = stmt.where(Authorization.source == source)
    rows = db.session.execute(stmt.order_by(Authorization.created_at.desc(), Authorization.id.desc())).scalars().all()
    heads = _heads(rows)
    data = [_row_dict(row, heads) for row in rows]
    if state:
        data = [row for row in data if row["effective_state"] == state]
    return jsonify({"ok": True, "data": data})


@bp.route("/upload", methods=["POST"])
@_manage_required
def upload_document():
    file = request.files.get("file")
    if file is None or not file.filename:
        return _error("未收到凭证 PDF")
    name = _safe_name(file.filename)
    if os.path.splitext(name)[1].lower() != ".pdf":
        return _error("凭证只允许上传 PDF 文件")
    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if size > _MAX_FILE_SIZE:
        return _error("凭证 PDF 不能超过 20MB", 413)
    month = datetime.now().strftime("%Y%m")
    directory = os.path.join(_ROOT, month)
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{int(time.time() * 1000)}_{name}")
    file.save(path)
    return jsonify({"ok": True, "path": path, "name": name})


@bp.route("", methods=["POST"])
@_manage_required
def create_authorization():
    data = request.get_json(force=True) or {}
    source = (data.get("source") or "").strip()
    if source not in _SOURCES:
        return _error("授权来源不正确")
    if source == "delegate" and session.get("role") not in ("dept", "dept_manage", "dept_demand"):
        return _error("委托授权只能由科室账号发起", 403)
    if source == "resolution" and not _full_hospital():
        return _error("决议授权只能由系统管理员或采购部助理发起", 403)

    username = (data.get("grantee_username") or "").strip()
    grantee = db.session.execute(db.select(User).filter_by(username=username, active=1)).scalar_one_or_none()
    if not grantee:
        return _error("被授权账号不存在或已停用")
    if not grantee.dept_code:
        return _error("被授权账号未绑定所属科室")
    # 决议授权的经办人固定属于采购部；不让客户端自报科室，避免伪造授权来源。
    granter_dept_code = session.get("dept_code", "") if source == "delegate" else "CGB"
    dept = db.session.execute(db.select(Dept).filter_by(code=granter_dept_code, active=1)).scalar_one_or_none()
    if not dept:
        return _error("授权人所在科室不存在或已停用")
    if source == "delegate" and not (dept.head_name or "").strip():
        return _error("本科室尚未维护负责人，不能发起委托授权")
    if source == "delegate" and grantee.dept_code != granter_dept_code:
        return _error("委托授权只能授给本科室账号")

    raw_keys = data.get("perm_keys")
    keys = list(dict.fromkeys(raw_keys)) if isinstance(raw_keys, list) and all(isinstance(k, str) for k in raw_keys) else []
    if not keys:
        return _error("至少选择一项权限")
    invalid = [key for key in keys if key not in ALL_PERM_KEYS]
    if invalid:
        return _error(f"包含未知权限：{'、'.join(invalid)}")
    if source == "delegate":
        own = set(get_user_perms(session["user"], session["role"]))
        excess = [key for key in keys if key not in own]
        if excess:
            return _error(f"不得授出本科室账号没有的权限：{'、'.join(excess)}")

    valid_from = (data.get("valid_from") or "").strip()
    valid_to = (data.get("valid_to") or "").strip()
    try:
        from_date = _parse_date(valid_from, "开始日期")
        to_date = _parse_date(valid_to, "结束日期")
    except ValueError as exc:
        return _error(str(exc))
    if to_date < from_date:
        return _error("结束日期不得早于开始日期")
    doc_no = (data.get("doc_no") or "").strip()
    if source == "resolution" and not doc_no:
        return _error("决议授权必须填写决议文号")
    doc_path = (data.get("doc_path") or "").strip()
    doc_name = _safe_name(data.get("doc_name") or "")
    if not doc_path or not doc_name or not _inside_upload_root(doc_path) or not os.path.isfile(doc_path):
        return _error("凭证 PDF 必传，请重新上传")
    if os.path.splitext(doc_path)[1].lower() != ".pdf":
        return _error("凭证只允许使用已上传的 PDF 文件")

    auth = Authorization(
        grantee_username=grantee.username, grantee_name=grantee.display_name,
        grantee_dept_code=grantee.dept_code, source=source,
        granter_name=dept.head_name if source == "delegate" else session.get("display_name", ""),
        granter_dept_code=granter_dept_code, granter_head_snapshot=dept.head_name or "",
        doc_no=doc_no, perm_keys=json.dumps(keys, ensure_ascii=False),
        valid_from=valid_from, valid_to=valid_to, doc_path=os.path.abspath(doc_path), doc_name=doc_name,
        status="active", created_by=session.get("user", ""),
    )
    db.session.add(auth)
    db.session.flush()
    _audit("grant", auth, {"authorization_id": auth.id, "source": source, "perm_keys": keys,
                            "valid_from": valid_from, "valid_to": valid_to})
    db.session.commit()
    return jsonify({"ok": True, "data": _row_dict(auth, {dept.code: dept.head_name or ""})}), 201


@bp.route("/<int:auth_id>/revoke", methods=["POST"])
@_manage_required
def revoke_authorization(auth_id):
    auth = db.session.get(Authorization, auth_id)
    if not auth:
        return _error("授权记录不存在", 404)
    if session.get("role") in ("dept", "dept_manage", "dept_demand") and auth.granter_dept_code != session.get("dept_code", ""):
        return _error("只能撤销本科室发出的授权", 403)
    if auth.status == "revoked":
        return _error("该授权已经撤销")
    reason = ((request.get_json(silent=True) or {}).get("reason") or "").strip()
    if not reason:
        return _error("撤销原因不能为空")
    auth.status = "revoked"
    auth.revoked_by = session.get("user", "")
    auth.revoked_at = datetime.now()
    auth.revoke_reason = reason
    _audit("revoke", auth, {"authorization_id": auth.id, "reason": reason})
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/my", methods=["GET"])
@login_required
def my_authorizations():
    rows = db.session.execute(
        db.select(Authorization).filter_by(grantee_username=session["user"])
        .order_by(Authorization.created_at.desc(), Authorization.id.desc())
    ).scalars().all()
    heads = _heads(rows)
    return jsonify({"ok": True, "data": [_row_dict(row, heads) for row in rows]})


@bp.route("/perm-catalog", methods=["GET"])
@login_required
def perm_catalog():
    return jsonify({"ok": True, "data": PERMISSION_CATALOG})


@bp.route("/users", methods=["GET"])
@_manage_required
def eligible_users():
    stmt = db.select(User).where(User.active == 1)
    if session.get("role") in ("dept", "dept_manage", "dept_demand"):
        stmt = stmt.where(User.dept_code == session.get("dept_code", ""))
    rows = db.session.execute(stmt.order_by(User.display_name, User.username)).scalars().all()
    return jsonify({"ok": True, "data": [row.to_dict() for row in rows]})


@bp.route("/depts", methods=["GET"])
@_manage_required
def active_depts():
    stmt = db.select(Dept).where(Dept.active == 1)
    if session.get("role") in ("dept", "dept_manage", "dept_demand"):
        stmt = stmt.where(Dept.code == session.get("dept_code", ""))
    rows = db.session.execute(stmt.order_by(Dept.sort_no, Dept.id)).scalars().all()
    return jsonify({"ok": True, "data": [row.to_dict() for row in rows]})


@bp.route("/<int:auth_id>/document", methods=["GET"])
@login_required
def download_document(auth_id):
    auth = db.session.get(Authorization, auth_id)
    if not auth:
        return _error("授权记录不存在", 404)
    is_grantee = auth.grantee_username == session.get("user")
    can_manage_row = _full_hospital() or (
        session.get("role") in ("dept", "dept_manage", "dept_demand") and auth.grantee_dept_code == session.get("dept_code", "")
    )
    if not is_grantee and not can_manage_row:
        return _error("无权限", 403)
    if not _inside_upload_root(auth.doc_path) or not os.path.isfile(auth.doc_path):
        return _error("凭证文件不存在", 404)
    return send_file(auth.doc_path, as_attachment=True, download_name=auth.doc_name)
