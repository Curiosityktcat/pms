"""后台「API 管理」：大模型 API 台账的增删改查、连通测试、一键启用。

- 台账行 = 一个 OpenAI 兼容端点（chat 或 embeddings）。
- 「启用」把该行写入 sys_config 全局模型键（scraper_model_* / embed_model_*），
  llm_client 全系统即时生效，无需重启。
- 测试统一走 curl 子进程：.12 透明代理下部分外网 API 用 requests 会挂死；
  key 经 curl -K 配置文件传入，不进 argv。
"""
import datetime
import json
import os
import subprocess
import tempfile
import time

from flask import Blueprint, request, jsonify

from models import db
from models.api_provider import ApiProvider
from models.sys_config import SysConfig
from routes.utils import admin_required
from services.llm_client import (
    CFG_MODEL_API, CFG_MODEL_NAME, CFG_API_KEY, CFG_TRANSPORT,
    CFG_EMBED_API, CFG_EMBED_NAME, CFG_EMBED_KEY,
)

bp = Blueprint("api_provider", __name__, url_prefix="/api/api-providers")


def _now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cfg_get(key):
    row = db.session.get(SysConfig, key)
    return (row.value or "") if row else ""


def _cfg_set(key, value):
    now = datetime.datetime.now().isoformat(timespec="seconds")
    row = db.session.get(SysConfig, key)
    if row is None:
        db.session.add(SysConfig(key=key, value=value, updated_at=now))
    else:
        row.value, row.updated_at = value, now


def _active_ids(rows):
    """当前生效的 chat / embed 台账行 id（按 URL+模型匹配 sys_config）。"""
    chat_api, chat_name = _cfg_get(CFG_MODEL_API), _cfg_get(CFG_MODEL_NAME)
    emb_api, emb_name = _cfg_get(CFG_EMBED_API), _cfg_get(CFG_EMBED_NAME)
    chat_id = embed_id = None
    for p in rows:
        if p.kind == "chat" and p.base_url == chat_api and p.model_name == chat_name:
            chat_id = p.id
        if p.kind == "embed" and p.base_url == emb_api and p.model_name == emb_name:
            embed_id = p.id
    return chat_id, embed_id


@bp.route("", methods=["GET"])
@admin_required
def list_providers():
    rows = ApiProvider.query.order_by(ApiProvider.sort, ApiProvider.id).all()
    chat_id, embed_id = _active_ids(rows)
    return jsonify({"ok": True,
                    "data": [p.to_dict() for p in rows],
                    "active_chat_id": chat_id, "active_embed_id": embed_id})


def _apply_body(p, body, *, is_new):
    p.name = (body.get("name") or "").strip() or p.name
    p.kind = body.get("kind") if body.get("kind") in ("chat", "embed") else (p.kind or "chat")
    p.base_url = (body.get("base_url") or "").strip() or (p.base_url if not is_new else "")
    p.model_name = (body.get("model_name") or "").strip() or (p.model_name if not is_new else "")
    p.transport = body.get("transport") if body.get("transport") in ("requests", "curl") else (p.transport or "requests")
    if "note" in body:
        p.note = (body.get("note") or "").strip()
    if "sort" in body:
        try:
            p.sort = int(body.get("sort") or 0)
        except (TypeError, ValueError):
            pass
    # key：新增必填；编辑时留空/传掩码 = 不改
    key = (body.get("api_key") or "").strip()
    if key and "…" not in key:
        p.api_key = key


@bp.route("", methods=["POST"])
@admin_required
def create_provider():
    body = request.get_json(force=True, silent=True) or {}
    if not (body.get("name") or "").strip():
        return jsonify({"ok": False, "error": "名称必填"}), 400
    if not (body.get("base_url") or "").strip():
        return jsonify({"ok": False, "error": "端点 URL 必填"}), 400
    p = ApiProvider(name="", api_key="")
    _apply_body(p, body, is_new=True)
    db.session.add(p)
    db.session.commit()
    return jsonify({"ok": True, "data": p.to_dict()})


@bp.route("/<int:pid>", methods=["PUT"])
@admin_required
def update_provider(pid):
    p = db.session.get(ApiProvider, pid)
    if p is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    _apply_body(p, request.get_json(force=True, silent=True) or {}, is_new=False)
    db.session.commit()
    return jsonify({"ok": True, "data": p.to_dict()})


@bp.route("/<int:pid>", methods=["DELETE"])
@admin_required
def delete_provider(pid):
    p = db.session.get(ApiProvider, pid)
    if p is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    rows = ApiProvider.query.all()
    chat_id, embed_id = _active_ids(rows)
    if pid in (chat_id, embed_id):
        return jsonify({"ok": False, "error": "该 API 正在全局启用中，先切换到其他 API 再删除"}), 400
    db.session.delete(p)
    db.session.commit()
    return jsonify({"ok": True})


# ── 连通测试（curl 子进程，代理环境下最可靠）────────────────────────
def _curl_json(url, key, payload, timeout=45):
    """POST JSON，返回 (http_code, body_dict_or_None, err_msg)。key 不进 argv。"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as pf:
        json.dump(payload, pf, ensure_ascii=False)
        payload_path = pf.name
    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as cf:
        cf.write(f'header = "Authorization: Bearer {key}"\n')
        cfg_path = cf.name
    try:
        r = subprocess.run(
            ["curl", "-sS", "-m", str(timeout), "-w", "\n%{http_code}",
             "-H", "Content-Type: application/json",
             "-K", cfg_path, "-d", f"@{payload_path}", url],
            capture_output=True, text=True, timeout=timeout + 10)
        if r.returncode != 0:
            return 0, None, (r.stderr or "curl 调用失败").strip()[:200]
        out = r.stdout.rsplit("\n", 1)
        code = int(out[-1] or 0)
        try:
            body = json.loads(out[0]) if out[0].strip() else None
        except json.JSONDecodeError:
            body = None
        return code, body, "" if body is not None else out[0][:200]
    except subprocess.TimeoutExpired:
        return 0, None, f"超时（>{timeout}s）"
    finally:
        for f in (payload_path, cfg_path):
            try:
                os.unlink(f)
            except OSError:
                pass


@bp.route("/<int:pid>/test", methods=["POST"])
@admin_required
def test_provider(pid):
    p = db.session.get(ApiProvider, pid)
    if p is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404

    if p.kind == "embed":
        payload = {"model": p.model_name, "input": ["连通性测试"]}
    else:
        payload = {"model": p.model_name, "max_tokens": 16,
                   "messages": [{"role": "user", "content": "连通性测试，请只回复：pong"}]}

    t0 = time.time()
    code, body, err = _curl_json(p.base_url, p.api_key, payload)
    ms = int((time.time() - t0) * 1000)

    ok, msg = False, ""
    if code == 200 and body:
        if p.kind == "embed":
            vec = ((body.get("data") or [{}])[0].get("embedding")) or []
            ok = bool(vec)
            msg = f"OK，维度 {len(vec)}，{ms}ms" if ok else "返回里没有向量"
        else:
            try:
                reply = (body["choices"][0]["message"].get("content") or
                         body["choices"][0]["message"].get("reasoning_content") or "").strip()
            except (KeyError, IndexError, TypeError):
                reply = ""
            ok = bool(reply)
            msg = f"OK，回复「{reply[:40]}」，{ms}ms" if ok else "HTTP 200 但没有内容"
    else:
        detail = ""
        if body and isinstance(body.get("error"), dict):
            detail = body["error"].get("message", "")[:120]
        msg = f"HTTP {code} {detail or err}".strip()

    p.last_test_ok = 1 if ok else 0
    p.last_test_at = _now()
    p.last_test_msg = msg[:300]
    db.session.commit()
    return jsonify({"ok": ok, "msg": msg, "ms": ms, "data": p.to_dict()})


@bp.route("/<int:pid>/activate", methods=["POST"])
@admin_required
def activate_provider(pid):
    """把该行设为全局对话（或嵌入）模型，llm_client 即时生效。"""
    p = db.session.get(ApiProvider, pid)
    if p is None:
        return jsonify({"ok": False, "error": "记录不存在"}), 404
    if not (p.base_url and p.model_name and p.api_key):
        return jsonify({"ok": False, "error": "端点 / 模型名 / key 不完整，无法启用"}), 400
    if p.kind == "embed":
        _cfg_set(CFG_EMBED_API, p.base_url)
        _cfg_set(CFG_EMBED_NAME, p.model_name)
        _cfg_set(CFG_EMBED_KEY, p.api_key)
    else:
        _cfg_set(CFG_MODEL_API, p.base_url)
        _cfg_set(CFG_MODEL_NAME, p.model_name)
        _cfg_set(CFG_API_KEY, p.api_key)
        _cfg_set(CFG_TRANSPORT, p.transport or "requests")
    db.session.commit()
    return jsonify({"ok": True, "msg": f"已启用「{p.name}」为全局{'嵌入' if p.kind == 'embed' else '对话'}模型"})
