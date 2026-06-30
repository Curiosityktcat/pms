import time
import datetime
import threading

from flask import Blueprint, request, jsonify, current_app

from models import db
from models.bid_board_project import BidBoardProject
from models.people import People
from models.sys_config import SysConfig
from services.bid_board_scraper import (
    run_scrape, WINDOW_DAYS,
    CFG_MODEL_API, CFG_MODEL_NAME, CFG_API_KEY,
    DEFAULT_MODEL_API, DEFAULT_MODEL_NAME, DEFAULT_API_KEY,
)
from routes.utils import login_required, admin_required

bp = Blueprint("bid_board", __name__, url_prefix="/api/bid-board")

COOLDOWN_SEC = 30 * 60  # 手动刷新冷却（沿用旧看板）

# 抓取任务进程内状态（全团队共享一个后台抓取）
_state = {"running": False, "last_run": 0.0, "last_msg": ""}
_lock = threading.Lock()


def _supervisors():
    """监督人员下拉：复用 pms 人员中 role_type='supervisor' 的在职人员。"""
    rows = db.session.execute(
        db.select(People).filter_by(role_type="supervisor", active=1).order_by(People.id)
    ).scalars().all()
    return [p.name for p in rows]


def _do_scrape():
    app = current_app._get_current_object()

    def worker():
        try:
            msg = run_scrape(app)
            _state["last_msg"] = msg
        except Exception as e:
            _state["last_msg"] = f"抓取出错: {e}"
        finally:
            _state["last_run"] = time.time()
            with _lock:
                _state["running"] = False

    threading.Thread(target=worker, daemon=True).start()


# ── 看板数据：未来14天内、按开标时间排序 ────────────────────────────
@bp.route("/data", methods=["GET"])
@login_required
def data():
    now = datetime.datetime.now().isoformat()
    end = (datetime.datetime.now() + datetime.timedelta(days=WINDOW_DAYS)).isoformat()
    rows = db.session.execute(
        db.select(BidBoardProject)
        .where(BidBoardProject.deadline_iso >= now)
        .where(BidBoardProject.deadline_iso <= end)
        .order_by(BidBoardProject.deadline_iso.asc())
    ).scalars().all()

    meta = db.session.get(SysConfig, "bid_board_last_run")
    return jsonify({
        "ok": True,
        "items": [r.to_dict() for r in rows],
        "updated_at": meta.value if meta else None,
        "supervisors": _supervisors(),
        "window_days": WINDOW_DAYS,
    })


# ── 指定/修改监督人员 ───────────────────────────────────────────────
@bp.route("/supervisor", methods=["POST"])
@login_required
def set_supervisor():
    d = request.get_json(silent=True) or {}
    number = (d.get("number") or "").strip()
    name = (d.get("name") or "").strip()
    if not number:
        return jsonify({"ok": False, "error": "缺少项目编号"}), 400
    row = db.session.get(BidBoardProject, number)
    if not row:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    row.supervisor = name
    db.session.commit()
    return jsonify({"ok": True})


# ── 手动刷新（30分钟冷却，后台抓取） ────────────────────────────────
@bp.route("/refresh", methods=["POST"])
@login_required
def refresh():
    with _lock:
        if _state["running"]:
            return jsonify({"status": "running"})
        el = time.time() - _state["last_run"]
        if _state["last_run"] and el < COOLDOWN_SEC:
            return jsonify({
                "status": "cooldown",
                "mins_ago": int(el // 60),
                "wait_mins": int((COOLDOWN_SEC - el) // 60) + 1,
            })
        _state["running"] = True
    _do_scrape()
    return jsonify({"status": "started"})


# ── 抓取状态轮询 ────────────────────────────────────────────────────
@bp.route("/status", methods=["GET"])
@login_required
def status():
    return jsonify({"running": _state["running"], "last_msg": _state["last_msg"]})


# ── 抓取模型设置（本地大模型离线时可切到在线模型） ──────────────────
def _mask(val):
    """API Key 脱敏：仅显示后 4 位。"""
    if not val or val == DEFAULT_API_KEY:
        return val
    return "****" + val[-4:] if len(val) > 4 else "****"


@bp.route("/model-config", methods=["GET"])
@admin_required
def get_model_config_api():
    def _v(key, default):
        row = db.session.get(SysConfig, key)
        return row.value if (row and row.value) else default
    return jsonify({"ok": True, "data": {
        "model_api":  _v(CFG_MODEL_API,  DEFAULT_MODEL_API),
        "model_name": _v(CFG_MODEL_NAME, DEFAULT_MODEL_NAME),
        "api_key":    _mask(_v(CFG_API_KEY, DEFAULT_API_KEY)),
        "default_api":  DEFAULT_MODEL_API,
        "default_name": DEFAULT_MODEL_NAME,
    }})


@bp.route("/model-config", methods=["PUT"])
@admin_required
def update_model_config_api():
    d = request.get_json(silent=True) or {}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    mapping = {
        CFG_MODEL_API:  d.get("model_api"),
        CFG_MODEL_NAME: d.get("model_name"),
        CFG_API_KEY:    d.get("api_key"),
    }
    for key, val in mapping.items():
        if val is None:
            continue
        # API Key 是脱敏值（****xxxx）则跳过，避免把掩码写回库
        if key == CFG_API_KEY and isinstance(val, str) and val.startswith("****"):
            continue
        row = db.session.get(SysConfig, key)
        if row:
            row.value = val
            row.updated_at = now
        else:
            db.session.add(SysConfig(key=key, value=val, updated_at=now))
    db.session.commit()
    return jsonify({"ok": True, "message": "模型配置已保存"})


@bp.route("/embed-config", methods=["GET"])
@admin_required
def get_embed_config_api():
    """嵌入模型配置（用于投标审查的语义检索）。未配置时各项为空。"""
    from services.llm_client import CFG_EMBED_API, CFG_EMBED_NAME, CFG_EMBED_KEY
    def _v(key):
        row = db.session.get(SysConfig, key)
        return row.value if (row and row.value) else ""
    return jsonify({"ok": True, "data": {
        "embed_api":  _v(CFG_EMBED_API),
        "embed_name": _v(CFG_EMBED_NAME),
        "embed_key":  _mask(_v(CFG_EMBED_KEY)),
        "suggest_api": "http://127.0.0.1:8890/v1/embeddings",
        "suggest_name": "bge-m3",
    }})


@bp.route("/embed-config", methods=["PUT"])
@admin_required
def update_embed_config_api():
    from services.llm_client import CFG_EMBED_API, CFG_EMBED_NAME, CFG_EMBED_KEY
    d = request.get_json(silent=True) or {}
    now = datetime.datetime.now().isoformat(timespec="seconds")
    mapping = {
        CFG_EMBED_API:  d.get("embed_api"),
        CFG_EMBED_NAME: d.get("embed_name"),
        CFG_EMBED_KEY:  d.get("embed_key"),
    }
    for key, val in mapping.items():
        if val is None:
            continue
        if key == CFG_EMBED_KEY and isinstance(val, str) and val.startswith("****"):
            continue
        row = db.session.get(SysConfig, key)
        if row:
            row.value = val
            row.updated_at = now
        else:
            db.session.add(SysConfig(key=key, value=val, updated_at=now))
    db.session.commit()
    return jsonify({"ok": True, "message": "嵌入模型配置已保存"})


@bp.route("/embed-config/test", methods=["POST"])
@admin_required
def test_embed_config_api():
    """用当前（或表单提交的）嵌入配置求一次向量，验证连通性与维度。"""
    from services.llm_client import embed, get_embed_config
    d = request.get_json(silent=True) or {}
    cfg = get_embed_config() or {"api": "", "name": "bge-m3", "key": "local"}
    if d.get("embed_api"):
        cfg["api"] = d["embed_api"]
    if d.get("embed_name"):
        cfg["name"] = d["embed_name"]
    if d.get("embed_key") and not str(d["embed_key"]).startswith("****"):
        cfg["key"] = d["embed_key"]
    if not cfg.get("api"):
        return jsonify({"ok": False, "error": "请先填写嵌入接口地址"}), 200
    vecs = embed(["连接测试"], cfg=cfg, timeout=20)
    if vecs and vecs[0]:
        return jsonify({"ok": True,
                        "message": f"连接成功：{cfg['name']} @ {cfg['api']}（向量维度 {len(vecs[0])}）"})
    return jsonify({"ok": False, "error": "连接失败：未取得有效向量，请检查地址/模型名/服务是否启动"}), 200


@bp.route("/model-config/test", methods=["POST"])
@admin_required
def test_model_config_api():
    """用当前（或表单提交的）配置向模型发一次极简请求，验证连通性。"""
    import requests
    from services.bid_board_scraper import get_model_config

    d = request.get_json(silent=True) or {}
    cfg = get_model_config()
    # 表单里填了就用表单的（api_key 为掩码则用已存的）
    if d.get("model_api"):
        cfg["api"] = d["model_api"]
    if d.get("model_name"):
        cfg["name"] = d["model_name"]
    if d.get("api_key") and not str(d["api_key"]).startswith("****"):
        cfg["key"] = d["api_key"]

    payload = {
        "model": cfg["name"],
        "messages": [{"role": "user", "content": "ping，请回复 ok"}],
        "max_tokens": 5,
        "temperature": 0,
    }
    try:
        r = requests.post(
            cfg["api"],
            headers={"Authorization": f"Bearer {cfg['key']}",
                     "Content-Type": "application/json"},
            json=payload, timeout=20,
        )
        if r.status_code in (400, 422):
            # 极简请求一般不会触发，这里只要能返回结构化错误就说明连得上
            r.raise_for_status()
        r.raise_for_status()
        _ = r.json()["choices"][0]["message"]
        return jsonify({"ok": True, "message": f"连接成功：{cfg['name']} @ {cfg['api']}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"连接失败：{e}"}), 200
