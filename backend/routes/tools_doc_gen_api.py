"""独立工具：AI 采购文件生成（不绑定项目，工具集合入口）。

上传「初稿/模板」+「采购需求」两个 Word → DeepSeek 段落级修订生成定稿 →
后台线程执行，前端轮询，完成后下载 docx。计费同全站（内部账号免、代理机构按 token）。
复用 services.procurement_doc_gen.generate_final_doc。
"""
import datetime
import os
import tempfile
import threading
import uuid

from flask import Blueprint, request, session, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

from routes.utils import login_required

bp = Blueprint("tools_doc_gen", __name__, url_prefix="/api/tools/doc-gen")

# job_id -> {running, ok, msg, summary, edits, usage, out_path, out_name}
_jobs: dict = {}
_lock = threading.Lock()
_JOB_TTL = 3600  # 1 小时后清理产物


def _prune():
    now = datetime.datetime.now().timestamp()
    for jid in list(_jobs):
        j = _jobs[jid]
        if not j.get("running") and now - j.get("_ts", now) > _JOB_TTL:
            p = j.get("out_path")
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
            _jobs.pop(jid, None)


def _save_upload(f, dst_dir):
    name = os.path.basename(f.filename or "")
    ext = os.path.splitext(name)[1].lower()
    if ext not in (".doc", ".docx"):
        return None, "仅支持 Word（doc/docx）文件"
    safe = secure_filename(name) or f"f{uuid.uuid4().hex}{ext}"
    if not safe.endswith(ext):
        safe += ext
    path = os.path.join(dst_dir, f"{uuid.uuid4().hex}_{safe}")
    f.save(path)
    return path, None


@bp.route("/start", methods=["POST"])
@login_required
def start():
    _prune()
    draft_f = request.files.get("draft")
    demand_f = request.files.get("demand")
    if not draft_f or not draft_f.filename or not demand_f or not demand_f.filename:
        return jsonify({"ok": False, "error": "请同时上传「初稿/模板」和「采购需求」两个 Word 文件"}), 400

    # 代理机构余额拦截（内部账号不计费）
    role = session.get("role", "")
    agency_code = session.get("agency_code", "") if role == "agency" else ""
    if agency_code:
        from services.billing import get_balance
        bal = get_balance(agency_code)
        if bal is not None and bal <= 0:
            return jsonify({"ok": False, "error": "AI 余额不足，请联系采购部充值后再使用"}), 402

    work_dir = tempfile.mkdtemp(prefix="docgen_")
    draft_path, err = _save_upload(draft_f, work_dir)
    if err:
        return jsonify({"ok": False, "error": f"初稿/模板：{err}"}), 400
    demand_path, err = _save_upload(demand_f, work_dir)
    if err:
        return jsonify({"ok": False, "error": f"采购需求：{err}"}), 400

    out_name = (request.form.get("out_name") or "采购文件（AI定稿）").strip()
    if not out_name.endswith(".docx"):
        out_name += ".docx"
    out_path = os.path.join(work_dir, f"out_{uuid.uuid4().hex}.docx")

    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"running": True, "ok": None, "msg": "AI 生成中（约 2~5 分钟）…",
                         "_ts": datetime.datetime.now().timestamp()}

    app = current_app._get_current_object()
    username = session.get("user", "")
    display = session.get("display_name", "")

    def _worker():
        try:
            from services.procurement_doc_gen import generate_final_doc
            with app.app_context():
                summary, applied, usage = generate_final_doc(draft_path, demand_path, out_path)
                from services import llm_usage
                llm_usage.record(username, display, "采购文件AI生成(工具)",
                                 "deepseek-v4-flash", usage, agency_code=agency_code)
            with _lock:
                _jobs[job_id] = {"running": False, "ok": True,
                                 "msg": f"生成完成，共 {len(applied)} 处修订",
                                 "summary": summary, "edits": applied, "usage": usage,
                                 "out_path": out_path, "out_name": out_name,
                                 "_ts": datetime.datetime.now().timestamp()}
        except Exception as e:  # noqa: BLE001
            with _lock:
                _jobs[job_id] = {"running": False, "ok": False,
                                 "msg": f"生成失败：{str(e)[:300]}",
                                 "_ts": datetime.datetime.now().timestamp()}

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "job_id": job_id})


@bp.route("/status/<job_id>")
@login_required
def status(job_id):
    j = _jobs.get(job_id)
    if not j:
        return jsonify({"ok": False, "error": "任务不存在或已过期"}), 404
    return jsonify({"ok": True, "data": {
        "running": j.get("running"), "ok": j.get("ok"), "msg": j.get("msg"),
        "summary": j.get("summary"), "edits": j.get("edits"), "usage": j.get("usage"),
        "has_file": bool(j.get("out_path")),
    }})


@bp.route("/download/<job_id>")
@login_required
def download(job_id):
    j = _jobs.get(job_id)
    if not j or not j.get("out_path") or not os.path.exists(j["out_path"]):
        return jsonify({"ok": False, "error": "文件不存在或已过期"}), 404
    return send_file(j["out_path"], as_attachment=True,
                     download_name=j.get("out_name") or "采购文件.docx")
