"""rd-web 合同审签单自动提交 API。

POST /api/rdweb/contract/submit
    body: {
        "data": {
            "合同名称": "...",
            "合同编码": "...",
            "项目名称及包号": "...",
            "归口管理科室": "...",
            "合同金额": "...",
            "合同甲方": "...",
            "甲方法定代表人": "...",
            "甲方联系电话": "...",
            "甲方地址": "...",
            "合同乙方": "...",
            "乙方法定代表人": "...",
            "乙方联系电话": "...",
            "乙方地址": "...",
            "合同类别": "采购部合同",
            "经办人": "黄新博"
        },
        "file_path": "/abs/path/to/contract.docx"   // 可选
    }

GET /api/rdweb/contract/status
    返回当前异步任务状态

GET /api/rdweb/contract/fields
    返回字段说明（供前端渲染表单）
"""
import datetime
import json
import os
import threading
import time

from flask import Blueprint, request, jsonify, current_app, session
from werkzeug.utils import secure_filename

from models import db
from models.rdweb_push_log import RdwebPushLog
from routes.utils import login_required, get_rdweb_creds

bp = Blueprint("rdweb_contract", __name__, url_prefix="/api/rdweb/contract")

_lock  = threading.Lock()
# 一次推送最长按 8 分钟算（Playwright 走完登录→填表→传附件→提交通常 1-3 分钟）。
# 超过就认为线程僵死，下一次推送直接接管，不让全局锁把功能永久锁死。
STALE_SEC = 8 * 60
_state = {
    "running":    False,
    "ok":         None,
    "serial_no":  "",
    "msg":        "",
    "last_run":   0,
    "started_at": 0,      # 本次任务开始时间，用于判定僵死
    "detail":     {},
}

FIELD_DEFS = [
    {"key": "合同名称",        "required": True,  "hint": "合同完整标题"},
    {"key": "合同编码",        "required": True,  "hint": "合同流水编号"},
    {"key": "项目名称及包号",  "required": True,  "hint": "对应采购项目名称和包号"},
    {"key": "归口管理科室",    "required": True,  "hint": "如：采购部"},
    {"key": "合同金额",        "required": True,  "hint": "含单位，如：¥100,000.00"},
    {"key": "合同甲方",        "required": True,  "hint": "甲方单位全称"},
    {"key": "甲方法定代表人",  "required": True,  "hint": "甲方法人名字"},
    {"key": "甲方联系电话",    "required": True,  "hint": "甲方联系电话"},
    {"key": "甲方地址",        "required": True,  "hint": "甲方注册地址"},
    {"key": "合同乙方",        "required": True,  "hint": "乙方单位全称"},
    {"key": "乙方法定代表人",  "required": True,  "hint": "乙方法人名字"},
    {"key": "乙方联系电话",    "required": True,  "hint": "乙方联系电话"},
    {"key": "乙方地址",        "required": True,  "hint": "乙方注册地址"},
    {"key": "合同类别",        "required": False, "hint": "采购部合同/其他合同/其他合同（已授权的简化流程）",
                                                   "options": ["采购部合同", "其他合同", "其他合同（已授权的简化流程）"]},
    {"key": "经办人",          "required": False, "hint": "如：黄新博"},
]


def _collect_attachments(body, file_path):
    """从请求体收集附件列表并校验（都须在工具上传目录下且存在）。
    优先取 body['attachments']（多附件），兼容旧的单 file_path。
    返回 (attachments, error_msg)；attachments = [{"path","name"}, ...]。"""
    items = body.get("attachments") or []
    result = []
    if items:
        for it in items:
            p = (it.get("path") or "").strip()
            if not p:
                continue
            if not os.path.exists(p) or not os.path.abspath(p).startswith(TOOL_UPLOAD_ROOT):
                return None, f"附件不存在或非法：{it.get('name') or p}，请重新上传"
            result.append({"path": p, "name": it.get("name") or os.path.basename(p)})
    elif file_path:
        if not os.path.exists(file_path):
            return None, f"文件不存在: {file_path}"
        result.append({"path": file_path, "name": os.path.basename(file_path)})
    return result, None


@bp.route("/fields")
@login_required
def get_fields():
    return jsonify({"ok": True, "fields": FIELD_DEFS})


@bp.route("/status")
@login_required
def get_status():
    return jsonify({"ok": True, "data": dict(_state)})


@bp.route("/submit", methods=["POST"])
@login_required
def submit():
    body = request.get_json(force=True, silent=True) or {}
    data      = body.get("data") or {}
    file_path = (body.get("file_path") or "").strip()

    # 校验必填字段
    missing = [f["key"] for f in FIELD_DEFS if f.get("required") and not data.get(f["key"])]
    if missing:
        return jsonify({"ok": False, "error": f"缺少必填字段: {', '.join(missing)}"}), 400

    # 附件：优先取 attachments 列表（多附件），兼容旧的单 file_path
    attachments, err = _collect_attachments(body, file_path)
    if err:
        return jsonify({"ok": False, "error": err}), 400
    if not attachments:
        return jsonify({"ok": False, "error": "rd-web 审签单要求必须上传附件"}), 400

    # 每人用自己的 rd-web 账号（避免都用黄新博账号推送）
    loginuser, password = get_rdweb_creds(session.get("display_name", ""))

    with _lock:
        # 卡死自愈：worker 是后台线程，一旦 Playwright 挂起且不返回，running 会永远为 True，
        # 之后每一次推送都被 429 拒绝、而且因为拒绝发生在落库之前，连失败记录都没有——
        # 表现就是「一直推不动又查不到原因」。超过 STALE_SEC 一律认定为僵死，放行本次。
        started = _state.get("started_at", 0)
        stale = _state["running"] and started and (time.time() - started > STALE_SEC)
        if _state["running"] and not stale:
            waited = int(time.time() - started) if started else 0
            return jsonify({"ok": False,
                            "error": f"上一个推送任务仍在运行（已 {waited} 秒），请稍后重试"}), 429
        if stale:
            print(f"[rdweb] 上一个任务已僵死 {int(time.time()-started)} 秒，自动解锁", flush=True)
        _state.update(running=True, ok=None, serial_no="", msg="", detail={},
                      last_run=0, started_at=time.time())

    # 推送记录落库（重启不丢）
    log = RdwebPushLog(
        username=session.get("user", ""),
        display_name=session.get("display_name", ""),
        contract_name=data.get("合同名称", ""),
        file_name="、".join(a["name"] for a in attachments)[:200],
        data_json=json.dumps(data, ensure_ascii=False),
        status="running",
    )
    db.session.add(log)
    db.session.commit()
    log_id = log.id

    app = current_app._get_current_object()

    def worker():
        from services.contract_submit import submit_contract
        try:
            res = submit_contract(data=data, attachments=attachments,
                                  loginuser=loginuser, password=password)
            ok, serial_no = res["ok"], res.get("serial_no", "")
            msg = res.get("msg", "")
            _state.update(running=False, ok=ok, serial_no=serial_no, msg=msg,
                          detail=res.get("detail", {}), last_run=int(time.time()))
        except Exception as e:
            ok, serial_no, msg = False, "", str(e)[:300]
            _state.update(running=False, ok=False, msg=msg,
                          serial_no="", last_run=int(time.time()))
        with app.app_context():
            row = db.session.get(RdwebPushLog, log_id)
            if row is not None:
                row.status = "ok" if ok else "fail"
                row.serial_no = serial_no
                row.msg = msg[:500]
                row.finished_at = datetime.datetime.now()
                db.session.commit()

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "任务已提交，正在后台执行", "async": True, "log_id": log_id})


@bp.route("/records")
@login_required
def records():
    """推送记录（最近 100 条）。

    单 worker 设计：内存态不在运行时，库里仍是 running 的记录必然是
    被服务重启杀掉的孤儿（留 60 秒宽限避开收尾竞态），标记为已中断。"""
    grace = datetime.datetime.now() - datetime.timedelta(seconds=60)
    dirty = False
    for row in RdwebPushLog.query.filter_by(status="running").all():
        if not _state["running"] and row.created_at and row.created_at < grace:
            row.status = "interrupted"
            row.msg = row.msg or "任务中断（服务重启或超时），未确认是否提交成功，请去 rd-web 核实后再重推"
            row.finished_at = datetime.datetime.now()
            dirty = True
    if dirty:
        db.session.commit()
    rows = (RdwebPushLog.query.order_by(RdwebPushLog.id.desc()).limit(100).all())
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/submit/sync", methods=["POST"])
@login_required
def submit_sync():
    """同步提交（等待完成后返回结果，适合脚本调用）。"""
    body = request.get_json(force=True, silent=True) or {}
    data      = body.get("data") or {}
    file_path = (body.get("file_path") or "").strip()

    missing = [f["key"] for f in FIELD_DEFS if f.get("required") and not data.get(f["key"])]
    if missing:
        return jsonify({"ok": False, "error": f"缺少必填字段: {', '.join(missing)}"}), 400

    attachments, aerr = _collect_attachments(body, file_path)
    if aerr:
        return jsonify({"ok": False, "error": aerr}), 400
    loginuser, password = get_rdweb_creds(session.get("display_name", ""))

    from services.contract_submit import submit_contract
    try:
        res = submit_contract(data=data, attachments=attachments,
                              loginuser=loginuser, password=password)
        return jsonify({"ok": res["ok"], "data": res})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── 常驻登录会话状态（谁还在线、上次登录多久了）────────────────────
@bp.route("/sessions", methods=["GET"])
@login_required
def rdweb_sessions():
    """rd-web 常驻会话状态。不含任何凭据，手机号打码。

    每个账号常驻一个已登录的浏览器，多个账号可以同时在线；
    复用会话意味着不必每次提交都登录一次（频繁登录会被站点限流）。
    """
    from services import rdweb_session
    return jsonify({"ok": True, "data": rdweb_session.status()})


@bp.route("/sessions/reset", methods=["POST"])
@login_required
def rdweb_session_reset():
    """强制丢弃本人的常驻会话，下次提交时重新登录（会话疑似坏掉时用）。"""
    from services import rdweb_session
    from routes.utils import get_rdweb_creds
    user, _ = get_rdweb_creds(session.get("display_name", ""))
    rdweb_session.session_for(user).invalidate()
    return jsonify({"ok": True, "message": "已重置，下次推送将重新登录"})


# ── 我的 rd-web 账号（每人用自己的账号推送，owner 恒为本人）─────────
@bp.route("/my-account", methods=["GET"])
@login_required
def my_account():
    """返回当前用户的 rd-web「执行」账号状态（手机号打码，不回传密码）。"""
    from models.project_distribution import RdwebAccount
    name = session.get("display_name", "")
    row = db.session.execute(
        db.select(RdwebAccount).filter_by(owner=name, usage="执行")
    ).scalar_one_or_none() if name else None
    if row and row.phone:
        masked = row.phone[:3] + "****" + row.phone[-4:] if len(row.phone) >= 7 else row.phone
        return jsonify({"ok": True, "configured": True, "phone_masked": masked,
                        "owner": name})
    # 未配置：回退公用账号
    return jsonify({"ok": True, "configured": False, "phone_masked": "",
                    "owner": name, "hint": "未配置个人 rd-web 账号，将回退使用公用账号推送"})


@bp.route("/my-account", methods=["POST"])
@login_required
def save_my_account():
    """新增/更新当前用户的 rd-web「执行」账号（owner 强制为本人，避免改到他人）。"""
    from models.project_distribution import RdwebAccount
    name = session.get("display_name", "")
    if not name:
        return jsonify({"ok": False, "error": "当前账号缺少姓名，无法绑定 rd-web 账号"}), 400
    body = request.get_json(force=True, silent=True) or {}
    phone = (body.get("phone") or "").strip()
    password = (body.get("password") or "").strip()
    if not phone or not password:
        return jsonify({"ok": False, "error": "请填写 rd-web 登录手机号与密码"}), 400
    row = db.session.execute(
        db.select(RdwebAccount).filter_by(owner=name, usage="执行")
    ).scalar_one_or_none()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if row:
        row.phone, row.password, row.updated_at = phone, password, now
    else:
        db.session.add(RdwebAccount(owner=name, phone=phone, password=password,
                                    usage="执行", note="本人在合同审签推送页自助绑定",
                                    updated_at=now))
    db.session.commit()
    return jsonify({"ok": True, "message": "已保存，本人后续推送将使用该账号"})


# ── 工具页「合同审签推送」：附件上传 + AI 自动填写 ─────────────────
_PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOL_UPLOAD_ROOT = os.path.join(_PMS_ROOT, "uploads", "rdweb_tool")
TOOL_ALLOWED = {".docx", ".doc", ".pdf", ".jpg", ".jpeg", ".png",
                ".xlsx", ".xls", ".zip"}


def _tool_safe_name(name: str) -> str:
    """保留中文文件名，仅剥离路径与危险字符（与我的模板同口径）。"""
    name = os.path.basename(name or "").replace("\x00", "").strip()
    if name in ("", ".", ".."):
        name = secure_filename(name) or "contract"
    return name


@bp.route("/upload", methods=["POST"])
@login_required
def upload_attachment():
    """上传审签附件，落盘后返回服务器绝对路径，供 /submit 的 file_path 使用。"""
    f = request.files.get("file")
    if f is None or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    name = _tool_safe_name(f.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in TOOL_ALLOWED:
        return jsonify({"ok": False,
                        "error": f"不支持的文件类型 {ext}，允许：{'、'.join(sorted(TOOL_ALLOWED))}"}), 400
    owner = _tool_safe_name(session.get("user", "")) or "_anonymous"
    d = os.path.join(TOOL_UPLOAD_ROOT, owner)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{int(time.time())}_{name}")
    f.save(path)
    return jsonify({"ok": True, "path": path, "name": name})


# AI 自动填写逻辑在 services/rdweb_autofill.py（与合同管理推送共用）
@bp.route("/autofill", methods=["POST"])
@login_required
def autofill():
    """合同附件（file_path，首选）或粘贴文字 → 大模型抽取审签单字段。"""
    from services.rdweb_autofill import extract_file_text, autofill_fields, FIELD_KEYS

    body = request.get_json(force=True, silent=True) or {}
    text = (body.get("text") or "").strip()
    file_path = (body.get("file_path") or "").strip()
    if file_path:
        if not os.path.exists(file_path) or not os.path.abspath(file_path).startswith(TOOL_UPLOAD_ROOT):
            return jsonify({"ok": False, "error": "附件不存在，请重新上传"}), 400
        try:
            text = extract_file_text(file_path)
        except RuntimeError as e:
            return jsonify({"ok": False, "error": str(e)}), 422
    if len(text) < 20:
        return jsonify({"ok": False, "error": "粘贴的合同内容太短，无法识别"}), 400

    usage_ctx = {"username": session.get("user", ""),
                 "display_name": session.get("display_name", ""),
                 "feature": "合同审签推送-自动填写"}
    try:
        out = autofill_fields(text, usage_ctx=usage_ctx,
                              operator=session.get("display_name", ""))
    except RuntimeError as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    filled = sum(1 for k in FIELD_KEYS if out.get(k))
    return jsonify({"ok": True, "data": out, "filled": filled})
