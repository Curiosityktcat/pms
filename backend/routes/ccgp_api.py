"""四川政府采购网 中标/合同公告看板 API  —  /api/ccgp"""
import time
import threading

from flask import Blueprint, request, jsonify, current_app

from models import db
from models.ccgp_notice import CcgpNotice
from models.sys_config import SysConfig
from services.ccgp_scraper import run_scrape, NOTICE_TYPES
from routes.utils import login_required

bp = Blueprint("ccgp", __name__, url_prefix="/api/ccgp")

COOLDOWN_SEC = 10 * 60   # 手动刷新冷却 10 分钟
_state = {"running": False, "last_run": 0.0, "last_msg": ""}
_lock = threading.Lock()


def _do_scrape(pages):
    app = current_app._get_current_object()

    def worker():
        try:
            _state["last_msg"] = run_scrape(app, pages=pages)
        except Exception as e:
            _state["last_msg"] = f"抓取出错: {e}"
        finally:
            _state["last_run"] = time.time()
            with _lock:
                _state["running"] = False

    threading.Thread(target=worker, daemon=True).start()


@bp.route("/data", methods=["GET"])
@login_required
def data():
    notice_type = request.args.get("type", "中标公告")
    if notice_type not in NOTICE_TYPES:
        notice_type = "中标公告"
    keyword = (request.args.get("keyword") or "").strip()
    page = max(request.args.get("page", 1, type=int), 1)
    page_size = min(request.args.get("page_size", 20, type=int), 100)

    q = db.select(CcgpNotice).where(CcgpNotice.notice_type == notice_type)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(db.or_(
            CcgpNotice.title.like(like),
            CcgpNotice.purchaser.like(like),
            CcgpNotice.agency.like(like),
            CcgpNotice.win_company.like(like),
            CcgpNotice.project_no.like(like),
        ))
    total = db.session.execute(
        db.select(db.func.count()).select_from(q.subquery())
    ).scalar() or 0
    rows = db.session.execute(
        q.order_by(CcgpNotice.notice_time.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).scalars().all()

    meta = db.session.get(SysConfig, "ccgp_last_run")
    return jsonify({
        "ok": True,
        "items": [r.to_dict() for r in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
        "updated_at": meta.value if meta else None,
    })


@bp.route("/detail/<nid>", methods=["GET"])
@login_required
def detail(nid):
    row = db.session.get(CcgpNotice, nid)
    if not row:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    return jsonify({"ok": True, "data": row.to_dict(with_content=True)})


@bp.route("/refresh", methods=["POST"])
@login_required
def refresh():
    pages = min((request.get_json(silent=True) or {}).get("pages", 3), 10)
    with _lock:
        if _state["running"]:
            return jsonify({"status": "running"})
        el = time.time() - _state["last_run"]
        if _state["last_run"] and el < COOLDOWN_SEC:
            return jsonify({"status": "cooldown",
                            "wait_mins": int((COOLDOWN_SEC - el) // 60) + 1})
        _state["running"] = True
    _do_scrape(pages)
    return jsonify({"status": "started"})


@bp.route("/status", methods=["GET"])
@login_required
def status():
    return jsonify({"running": _state["running"], "last_msg": _state["last_msg"]})
