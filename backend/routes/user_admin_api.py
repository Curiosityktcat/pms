"""系统管理员维护登录账号。"""
import json
import secrets
import string

from flask import Blueprint, jsonify, request, session

from models import db
from models.agency import Agency
from models.dept import Dept
from models.role_permission import RolePermission
from models.user import User
from models.user_audit_log import UserAuditLog
from routes.utils import ROLE_CN, admin_required
from services.auth import hash_pw
from services.permission import DEFAULT_ROLE_PERMS, ADMIN_USERNAME

bp = Blueprint("user_admin", __name__, url_prefix="/api/admin/users")

# admin 是唯一用户名特判，不是可分配的数据库角色；这里列的是现有可登录业务角色。
ROLES = ["assistant", "pd_assistant", "leader", "officer", "supervisor", "agency", "dept_manage", "dept_demand"]
ROLE_LABELS = {**ROLE_CN, "pd_assistant": "项目分发助理"}
DEPT_ROLES = ("dept", "dept_manage", "dept_demand")


def _dept_role(dept):
    """采购部虽属行后科室，但采管分离，不能据此获得归口管理角色。"""
    return "dept_manage" if dept.dept_type == "行后" and dept.code != "CGB" else "dept_demand"


def _error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def _audit(action, user, detail=None):
    db.session.add(UserAuditLog(
        actor=session.get("user", ""), actor_name=session.get("display_name", ""),
        action=action, target_id=user.id, target_username=user.username,
        detail=json.dumps(detail or {}, ensure_ascii=False),
    ))


def _password(length=12):
    # 保证三类字符都有，避免随机结果偶尔不符合常见密码复杂度要求。
    chars = string.ascii_letters + string.digits
    while True:
        value = "".join(secrets.choice(chars) for _ in range(length))
        if any(c.islower() for c in value) and any(c.isupper() for c in value) and any(c.isdigit() for c in value):
            return value


def _validate_binding(role, dept_code, agency_code):
    if role not in ROLES:
        return "未知角色"
    if role in DEPT_ROLES:
        if not dept_code:
            return "科室账号必须选择所属科室"
        dept = db.session.execute(db.select(Dept).filter_by(code=dept_code, active=1)).scalar_one_or_none()
        if not dept:
            return "所选科室不存在或已停用"
        expected = _dept_role(dept)
        if role != "dept" and role != expected:
            return f"该科室应使用{ROLE_LABELS[expected]}角色"
    if role == "agency":
        if not agency_code:
            return "代理机构账号必须选择所属代理机构"
        agency = db.session.execute(db.select(Agency).filter_by(code=agency_code, active=1)).scalar_one_or_none()
        if not agency:
            return "所选代理机构不存在或已停用"
    return ""


def _seed_role_if_empty(role):
    count = db.session.execute(
        db.select(db.func.count()).select_from(RolePermission).filter_by(role=role)
    ).scalar_one()
    if count == 0:
        for key in DEFAULT_ROLE_PERMS.get(role, []):
            db.session.add(RolePermission(role=role, perm_key=key))


# 已确认含账号或姓名业务归属的字段。删除必须保守：任一处命中即拒绝，绝不级联清理业务记录。
def _business_refs(user):
    # 业务模型很多且仍会增加。按“身份字段名”扫描已注册模型，比手列几张表更保守：
    # 项目、合同、审批、推送、消息、待办等只要存过用户名或姓名都会命中。
    identity_fields = {
        "username", "display_name", "officer", "operator", "operator_name", "owner", "owner_name",
        "sender", "sender_name", "recipient", "recipient_name", "created_by", "created_by_name",
        "updated_by", "uploaded_by", "done_by", "assigned_officer", "demand_confirmed_by", "doc_confirmed_by",
    }
    values = {v for v in (user.username, user.display_name) if v}
    total = 0
    ignored = {"users", "user_audit_logs", "role_permissions", "depts"}
    for mapper in db.Model.registry.mappers:
        model = mapper.class_
        if model.__tablename__ in ignored:
            continue
        columns = [getattr(model, column.key) for column in mapper.columns if column.key in identity_fields]
        if not columns:
            continue
        condition = db.or_(*(column.in_(values) for column in columns))
        total += db.session.execute(
            db.select(db.func.count()).select_from(model).where(condition)
        ).scalar_one()
    return total


@bp.route("", methods=["GET"])
@admin_required
def list_users():
    q = (request.args.get("q") or "").strip()
    role = (request.args.get("role") or "").strip()
    active = request.args.get("active")
    dept_code = (request.args.get("dept_code") or "").strip().upper()
    agency_code = (request.args.get("agency_code") or "").strip().upper()
    try:
        page = max(1, int(request.args.get("page", 1)))
        size = min(100, max(1, int(request.args.get("size", 20))))
    except (TypeError, ValueError):
        return _error("分页参数不正确")
    stmt = db.select(User)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(db.or_(User.username.like(like), User.display_name.like(like)))
    if role:
        stmt = stmt.where(User.role == role)
    if active in ("0", "1"):
        stmt = stmt.where(User.active == int(active))
    if dept_code:
        stmt = stmt.where(User.dept_code == dept_code)
    if agency_code:
        stmt = stmt.where(User.agency_code == agency_code)
    total = db.session.execute(db.select(db.func.count()).select_from(stmt.subquery())).scalar_one()
    rows = db.session.execute(stmt.order_by(User.id).offset((page - 1) * size).limit(size)).scalars().all()
    dept_map = {d.code: d.to_dict() for d in db.session.execute(db.select(Dept)).scalars()}
    data = []
    for user in rows:
        item = user.to_dict()
        item["dept"] = dept_map.get(user.dept_code) if user.dept_code else None
        data.append(item)
    return jsonify({"ok": True, "data": data, "total": total, "page": page, "size": size})


@bp.route("", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json(force=True) or {}
    username = (data.get("username") or "").strip()
    display_name = (data.get("display_name") or "").strip()
    role = (data.get("role") or "").strip()
    dept_code = (data.get("dept_code") or "").strip().upper() if role in DEPT_ROLES else ""
    agency_code = (data.get("agency_code") or "").strip().upper() if role == "agency" else ""
    if not username or not display_name:
        return _error("用户名和姓名不能为空")
    if db.session.execute(db.select(User.id).filter_by(username=username)).scalar_one_or_none() is not None:
        return _error("用户名已存在")
    error = _validate_binding(role, dept_code, agency_code)
    if error:
        return _error(error)
    password = str(data.get("password") or "") or _password()
    if len(password) < 6:
        return _error("密码至少 6 位")
    salt = secrets.token_hex(16)
    user = User(username=username, display_name=display_name, role=role, active=1,
                dept_code=dept_code, agency_code=agency_code,
                salt=salt, pw_hash=hash_pw(password, salt))
    db.session.add(user)
    db.session.flush()
    _seed_role_if_empty(role)
    _audit("create", user, {"username": {"before": None, "after": username},
                            "display_name": {"before": None, "after": display_name},
                            "role": {"before": None, "after": role}})
    db.session.commit()
    return jsonify({"ok": True, "user": user.to_dict(), "password": password}), 201


@bp.route("/<int:user_id>", methods=["PUT"])
@admin_required
def update_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return _error("账号不存在", 404)
    data = request.get_json(force=True) or {}
    role = (data.get("role", user.role) or "").strip()
    display_name = (data.get("display_name", user.display_name) or "").strip()
    dept_code = (data.get("dept_code", user.dept_code) or "").strip().upper() if role in DEPT_ROLES else ""
    agency_code = (data.get("agency_code", user.agency_code) or "").strip().upper() if role == "agency" else ""
    active = 1 if data.get("active", user.active) in (1, True, "1") else 0
    if not display_name:
        return _error("姓名不能为空")
    if user.username == ADMIN_USERNAME and (role != user.role or active == 0):
        return _error("不能停用管理员自己或修改管理员自己的角色")
    error = _validate_binding(role, dept_code, agency_code)
    if error:
        return _error(error)
    # 必须在赋新姓名前查旧姓名，否则提示会漏掉历史数据中的旧字符串。
    name_refs = _business_refs(user) if display_name != user.display_name else 0
    changes = {}
    for field, value in (("display_name", display_name), ("role", role), ("dept_code", dept_code),
                         ("agency_code", agency_code), ("active", active)):
        old = getattr(user, field) or (0 if field == "active" else "")
        if old != value:
            changes[field] = {"before": old, "after": value}
            setattr(user, field, value)
    if changes:
        _seed_role_if_empty(role)
        _audit("update", user, changes)
        db.session.commit()
    return jsonify({"ok": True, "user": user.to_dict(), "name_reference_count": name_refs,
                    "warning": f"该姓名在业务数据里被引用了 {name_refs} 处" if "display_name" in changes else ""})


@bp.route("/<int:user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return _error("账号不存在", 404)
    data = request.get_json(silent=True) or {}
    password = str(data.get("password") or "") or _password()
    if len(password) < 6:
        return _error("密码至少 6 位")
    salt = secrets.token_hex(16)
    user.salt, user.pw_hash = salt, hash_pw(password, salt)
    # 审计只记动作，刻意不把密码、salt、hash 放进 detail。
    _audit("reset_pwd", user, {"message": "重置了密码"})
    db.session.commit()
    return jsonify({"ok": True, "password": password})


@bp.route("/<int:user_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return _error("账号不存在", 404)
    if user.username == ADMIN_USERNAME and user.active:
        return _error("不能停用管理员自己")
    old = int(bool(user.active))
    user.active = 0 if old else 1
    _audit("toggle", user, {"active": {"before": old, "after": user.active}})
    db.session.commit()
    return jsonify({"ok": True, "user": user.to_dict()})


@bp.route("/<int:user_id>", methods=["DELETE"])
@admin_required
def delete_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return _error("账号不存在", 404)
    if user.username == ADMIN_USERNAME:
        return _error("不能删除管理员自己")
    try:
        refs = _business_refs(user)
    except Exception:
        # 删除宁可多拒绝也不能误删：新增业务表尚未纳入检查时，异常即视为无法判断。
        return _error("无法完整判断该账号的业务痕迹，请停用账号，不要删除")
    if refs:
        return _error(f"该账号已有 {refs} 处业务痕迹，只能停用，不能删除")
    _audit("delete", user, {"deleted": {"before": False, "after": True}})
    db.session.delete(user)
    db.session.commit()
    return jsonify({"ok": True})


@bp.route("/roles", methods=["GET"])
@admin_required
def roles():
    counts = dict(db.session.execute(
        db.select(User.role, db.func.count(User.id)).group_by(User.role)
    ).all())
    return jsonify({"ok": True, "data": [
        {"role": role, "role_cn": ROLE_LABELS.get(role, role), "count": counts.get(role, 0)}
        for role in ROLES
    ]})


@bp.route("/bulk-dept-accounts", methods=["POST"])
@admin_required
def bulk_dept_accounts():
    """为尚未绑定账号的启用科室批量建号；明文密码只存在于本次响应的局部变量。"""
    data = request.get_json(silent=True) or {}
    dry_run = data.get("dry_run") in (True, 1, "1", "true")
    bound_codes = set(db.session.execute(
        db.select(User.dept_code).where(User.dept_code != "")
    ).scalars())
    depts = db.session.execute(
        db.select(Dept).filter_by(active=1).order_by(Dept.sort_no, Dept.id)
    ).scalars().all()
    pending = [dept for dept in depts if dept.code not in bound_codes]
    preview = [{"username": dept.name, "display_name": dept.name,
                "role": _dept_role(dept), "dept_code": dept.code,
                "dept_type": dept.dept_type or ""} for dept in pending]
    if dry_run:
        return jsonify({"ok": True, "dry_run": True, "created": [], "pending": preview,
                        "created_count": 0, "pending_count": len(preview)})

    existing_names = set(db.session.execute(db.select(User.username)).scalars())
    conflicts = [dept.name for dept in pending if dept.name in existing_names]
    if conflicts:
        return _error(f"以下科室名已被其它账号占用：{'、'.join(conflicts)}")

    created = []
    for dept in pending:
        password = _password()
        salt = secrets.token_hex(16)
        user = User(username=dept.name, display_name=dept.name, role=_dept_role(dept), active=1,
                    dept_code=dept.code, agency_code="", salt=salt, pw_hash=hash_pw(password, salt))
        db.session.add(user)
        db.session.flush()
        _seed_role_if_empty(user.role)
        # 审计保留建号事实即可；密码及其派生值绝不能进入 detail。
        _audit("create", user, {"source": "bulk_dept_accounts", "role": user.role,
                                "dept_code": dept.code})
        created.append({"username": user.username, "display_name": user.display_name,
                        "role": user.role, "dept_code": user.dept_code,
                        "dept_type": dept.dept_type or "", "password": password})
    db.session.commit()
    return jsonify({"ok": True, "dry_run": False, "created": created, "pending": [],
                    "created_count": len(created), "pending_count": 0})


@bp.route("/<int:user_id>/audit", methods=["GET"])
@admin_required
def user_audit(user_id):
    user = db.session.get(User, user_id)
    if not user:
        return _error("账号不存在", 404)
    rows = db.session.execute(
        db.select(UserAuditLog).where(
            db.or_(UserAuditLog.target_id == user_id, UserAuditLog.target_username == user.username)
        ).order_by(UserAuditLog.created_at.desc(), UserAuditLog.id.desc())
    ).scalars().all()
    return jsonify({"ok": True, "data": [row.to_dict() for row in rows]})
