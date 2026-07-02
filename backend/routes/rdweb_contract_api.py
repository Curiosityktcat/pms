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
import json
import os
import threading
import time

from flask import Blueprint, request, jsonify, current_app

from routes.utils import login_required

bp = Blueprint("rdweb_contract", __name__, url_prefix="/api/rdweb/contract")

_lock  = threading.Lock()
_state = {
    "running":   False,
    "ok":        None,
    "serial_no": "",
    "msg":       "",
    "last_run":  0,
    "detail":    {},
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

    if file_path and not os.path.exists(file_path):
        return jsonify({"ok": False, "error": f"文件不存在: {file_path}"}), 400

    with _lock:
        if _state["running"]:
            return jsonify({"ok": False, "error": "上一个任务仍在运行，请稍后重试"}), 429
        _state.update(running=True, ok=None, serial_no="", msg="", detail={}, last_run=0)

    app = current_app._get_current_object()

    def worker():
        from services.contract_submit import submit_contract
        try:
            res = submit_contract(data=data, file_path=file_path)
            _state.update(
                running=False,
                ok=res["ok"],
                serial_no=res.get("serial_no", ""),
                msg=res.get("msg", ""),
                detail=res.get("detail", {}),
                last_run=int(time.time()),
            )
        except Exception as e:
            _state.update(
                running=False,
                ok=False,
                msg=str(e)[:300],
                serial_no="",
                last_run=int(time.time()),
            )

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "任务已提交，正在后台执行", "async": True})


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

    from services.contract_submit import submit_contract
    try:
        res = submit_contract(data=data, file_path=file_path)
        return jsonify({"ok": res["ok"], "data": res})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
