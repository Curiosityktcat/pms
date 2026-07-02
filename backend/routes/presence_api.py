"""在线人数  —  /api/presence

内存级在线状态：每个登录用户打开/刷新页面时 ping 一次，记录 last_seen。
统计窗口（WINDOW 秒）内活跃的用户数即为在线人数。
后端是单进程 Flask（app.run），内存存储即可，无需建表。
"""
import threading
import time

from flask import Blueprint, session, jsonify

from routes.utils import login_required

bp = Blueprint("presence", __name__, url_prefix="/api/presence")

WINDOW = 120  # 秒：超过此时长未 ping 视为离线

_lock = threading.Lock()
_seen: dict[str, float] = {}  # username -> last_seen_epoch


@bp.route("/ping", methods=["GET", "POST"])
@login_required
def ping():
    """记录当前用户在线并返回在线人数（只给数字，不返回名单）。前端每次刷新/轮询时调用。"""
    me = session.get("user", "")
    now = time.time()
    with _lock:
        if me:
            _seen[me] = now
        cutoff = now - WINDOW
        for u in [u for u, ts in _seen.items() if ts < cutoff]:
            del _seen[u]
        count = len(_seen)
    return jsonify({"ok": True, "data": {"count": count}})
