"""指挥 Hermes 去 rd-web 自动填报的 PMS 端接口。

流程：PMS 收集/确认业务信息 → POST /api/hermes/submit → 调 Hermes(8645) → 落库跟踪
     → 前端轮询 /api/hermes/status/<task_id>（或 Hermes 回调 /api/hermes/callback）。
"""
import json
import os
import time
import datetime

from flask import Blueprint, request, jsonify, session

from models import db
from models.hermes_task import HermesTask
from routes.utils import login_required
from services import hermes_client

bp = Blueprint("hermes", __name__, url_prefix="/api/hermes")

_UPLOADS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "uploads"))


def _contract_attachments(contract_id):
    """解析合同的「合同草案」附件 + 该项目本轮「中标通知书」，返回 [{type,name,path}]（绝对路径，供同机 Hermes 读取）。"""
    from models.contract import Contract
    from models.contract_attachment import ContractAttachment
    from models.procurement_doc_attachment import ProcurementDocAttachment
    out = []
    c = db.session.get(Contract, contract_id)
    if not c:
        return out
    # 合同草案附件
    for a in db.session.execute(
        db.select(ContractAttachment).filter_by(contract_id=contract_id, stage="草案")
    ).scalars().all():
        p = os.path.join(_UPLOADS, "contracts", str(contract_id), "attachments", a.saved_name or "")
        if a.saved_name and os.path.exists(p):
            out.append({"type": "合同草案", "name": a.original_name or a.saved_name, "path": p})
    # 中标通知书（按项目，取最新一份）
    notices = db.session.execute(
        db.select(ProcurementDocAttachment).filter_by(project_id=c.project_id, kind="award_notice")
        .order_by(ProcurementDocAttachment.id.desc())
    ).scalars().all()
    for a in notices[:1]:
        p = os.path.join(_UPLOADS, "procurement_result", str(c.project_id), a.saved_name or "")
        if a.saved_name and os.path.exists(p):
            out.append({"type": "中标通知书", "name": a.original_name or a.saved_name, "path": p})
    return out

TYPE_CN = {
    "agency-agreement": "代理协议审签",
    "procurement-approval": "采购项目审批",
    "procurement-contract": "采购合同审签",
}
# PMS 自身端口（供 Hermes 完成后回调）
PMS_CALLBACK = "http://127.0.0.1:1573/api/hermes/callback"


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


@bp.route("/submit", methods=["POST"])
@login_required
def submit():
    body = request.get_json(force=True) or {}
    task_type = (body.get("task_type") or "").strip()
    if task_type not in TYPE_CN:
        return jsonify({"ok": False, "error": "未知业务类型"}), 400
    action = (body.get("action") or "create").strip()
    data = body.get("data") or {}
    project_id = body.get("project_id")
    # 合同审签：按 contract_id 解析「合同草案+中标通知书」附件，随载荷发给 Hermes
    contract_id = body.get("contract_id")
    if contract_id:
        try:
            data["附件"] = _contract_attachments(int(contract_id))
        except Exception:
            data["附件"] = []
    title = (body.get("title") or data.get("项目名称及包号") or data.get("项目名称") or "").strip()
    stamp = int(time.time()) % 1000000
    base = (data.get("项目编号") or "PMS").strip()
    tid = f"{base}-{task_type[:4]}-{stamp}"

    try:
        resp = hermes_client.submit(task_type, tid, action, data, PMS_CALLBACK)
    except Exception as e:
        return jsonify({"ok": False,
                        "error": f"Hermes 服务调用失败：{e}（请确认 pms_api_server.py 在运行）"}), 502

    t = HermesTask(
        task_id=tid, task_type=task_type, action=action, project_id=project_id, title=title,
        data=json.dumps(data, ensure_ascii=False),
        status=resp.get("status", "accepted"), message=resp.get("message", ""),
        created_by=session.get("display_name", ""), created_at=_now(), updated_at=_now(),
    )
    db.session.add(t)
    db.session.commit()
    return jsonify({"ok": True, "data": t.to_dict()})


@bp.route("/status/<task_id>", methods=["GET"])
@login_required
def task_status(task_id):
    t = db.session.execute(db.select(HermesTask).filter_by(task_id=task_id)).scalar_one_or_none()
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    if t.status not in ("completed", "failed"):
        try:
            s = hermes_client.status(task_id)
            t.status = s.get("status", t.status)
            t.progress = s.get("progress", t.progress) or ""
            t.message = s.get("message", t.message) or ""
            if s.get("result"):
                t.result = json.dumps(s["result"], ensure_ascii=False)
            t.updated_at = _now()
            db.session.commit()
        except Exception:
            pass
    return jsonify({"ok": True, "data": t.to_dict()})


@bp.route("/callback", methods=["POST"])
def callback():
    """Hermes 完成后回调（localhost 内部，无需登录）。"""
    body = request.get_json(force=True, silent=True) or {}
    tid = body.get("task_id")
    if tid:
        t = db.session.execute(db.select(HermesTask).filter_by(task_id=tid)).scalar_one_or_none()
        if t:
            t.status = body.get("status", t.status)
            t.message = body.get("message", t.message) or ""
            if body.get("result"):
                t.result = json.dumps(body["result"], ensure_ascii=False)
            t.updated_at = _now()
            db.session.commit()
    return jsonify({"ok": True})


@bp.route("/tasks", methods=["GET"])
@login_required
def list_tasks():
    q = db.select(HermesTask).order_by(HermesTask.id.desc())
    pid = request.args.get("project_id")
    if pid and pid.isdigit():
        q = q.where(HermesTask.project_id == int(pid))
    tt = request.args.get("task_type")
    if tt:
        q = q.where(HermesTask.task_type == tt)
    rows = db.session.execute(q.limit(50)).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})
