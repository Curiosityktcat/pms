"""政采数据流水线看板 API —— /api/datapipe

仅「黄新博」本人可见（与私人文件库同门控）。数据源是 .12 上的 PostgreSQL `ccgp` 库，
以及本机的进程/端口探测，用来回答「现在到底在跑什么、跑到哪了」。
"""
import os
import socket
import subprocess
import time

import psycopg2
from flask import Blueprint, jsonify, session

from routes.utils import login_required

bp = Blueprint("datapipe", __name__, url_prefix="/api/datapipe")

OWNER = "黄新博"

PG = dict(host="127.0.0.1", port=5432, dbname="ccgp", user="ccgp",
          connect_timeout=5)

_cache = {"ts": 0.0, "data": None}
CACHE_SEC = 20


@bp.before_request
def _guard():
    if "user" not in session:
        return jsonify({"ok": False, "error": "未登录"}), 401
    if session.get("user") != OWNER:
        return jsonify({"ok": False, "error": "无权限：数据流水线看板仅限本人使用"}), 403
    return None


def _q(cur, sql, one=True):
    try:
        cur.execute(sql)
        if one:
            r = cur.fetchone()
            return r[0] if r else 0
        return cur.fetchall()
    except Exception:
        cur.connection.rollback()
        return 0 if one else []


def _port_open(port, host="127.0.0.1"):
    s = socket.socket()
    s.settimeout(1.5)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _pgrep(pattern):
    try:
        out = subprocess.run(["pgrep", "-fc", pattern], capture_output=True,
                             text=True, timeout=5).stdout.strip()
        return int(out or 0)
    except Exception:
        return 0


def collect():
    conn = psycopg2.connect(**PG)
    cur = conn.cursor()

    # ── 一、数据资产总量 ─────────────────────────────
    assets = {
        "公告": _q(cur, "SELECT count(*) FROM notice"),
        "项目": _q(cur, "SELECT count(*) FROM project"),
        "中标合同明细": _q(cur, "SELECT count(*) FROM product_item"),
        "联系人": _q(cur, "SELECT count(*) FROM org_contact"),
        "联系人带手机": _q(cur, "SELECT count(*) FROM org_contact WHERE mobile IS NOT NULL"),
        "技术分行": _q(cur, "SELECT count(*) FROM review_score"),
        "技术分达标": _q(cur, "SELECT count(*) FROM review_score WHERE tech_ratio>=0.95"),
        "采购需求文件": _q(cur, "SELECT count(*) FROM requirement_doc"),
        "设备技术参数": _q(cur, "SELECT count(*) FROM device_param"),
        "已抽参数设备": _q(cur, "SELECT count(DISTINCT name) FROM device_param"),
        "UDI产品标识": _q(cur, "SELECT count(*) FROM udi_device"),
        "UDI注册证": _q(cur, "SELECT count(DISTINCT reg_cert) FROM udi_device"),
        "附件已下载": _q(cur, "SELECT count(*) FROM attachment WHERE downloaded"),
    }

    # ── 二、各省抓取进度 ─────────────────────────────
    prov_rows = _q(cur, """
        SELECT n.province,
               count(*) AS 已入库,
               max(n.crawled_at) AS 最近入库
        FROM notice n GROUP BY 1 ORDER BY 2 DESC""", one=False)
    cursors = dict(_q(cur, """
        SELECT split_part(scope_key,'|',1) AS prov,
               count(*) FILTER (WHERE NOT done)
        FROM crawl_cursor WHERE scope_key ~ '^[^|]+\\|[^|]+\\|'
        GROUP BY 1""", one=False) or [])
    provinces = []
    for prov, cnt, last in prov_rows:
        pending = cursors.get(prov, 0)
        provinces.append({
            "省份": prov,
            "已入库": cnt,
            "未完成任务": pending,
            "状态": "抓取中" if pending else "已完成·日增量",
            "最近入库": last.strftime("%m-%d %H:%M") if last else "",
        })

    # ── 三、流水线队列深度 ───────────────────────────
    queues = [
        {"环节": "附件下载", "待办": _q(cur, """
            SELECT count(*) FROM attachment a JOIN notice n ON n.id=a.notice_id
            JOIN project p ON p.id=n.project_id
            WHERE a.downloaded=false AND a.is_zip_member=false
              AND COALESCE(p.is_centralized,false)=false AND p.province='四川'""")},
        {"环节": "OCR 待做", "待办": _q(cur,
            "SELECT count(*) FROM attachment WHERE downloaded AND ocr_status='pending'")},
        {"环节": "明细抽取", "待办": _q(cur,
            "SELECT count(*) FROM notice WHERE notice_type IN ('win','contract') AND items_extracted=false")},
        {"环节": "联系人抽取", "待办": _q(cur,
            "SELECT count(*) FROM notice WHERE contacts_extracted=false")},
        {"环节": "技术参数抽取(Qwen)", "待办": _q(cur,
            "SELECT count(*) FROM requirement_doc WHERE params_extracted=false")},
        {"环节": "技术分抽取", "待办": _q(cur, """
            SELECT count(*) FROM attachment WHERE downloaded AND score_parsed=false
              AND file_ext='.pdf' AND filename ~ '评审情况|评分表|得分表|评审结果表'""")},
    ]

    # ── 四、近 1 小时吞吐 ────────────────────────────
    rate = _q(cur, "SELECT count(*) FROM notice WHERE crawled_at > now() - interval '1 hour'")

    # ── 五、最近活动日志 ─────────────────────────────
    logs = _q(cur, """SELECT to_char(created_at,'MM-DD HH24:MI'), stage, left(msg, 90)
                      FROM crawl_log ORDER BY id DESC LIMIT 12""", one=False)

    cur.close()
    conn.close()

    # ── 六、服务与进程健康 ───────────────────────────
    services = [
        {"名称": "Qwen 抽取 (7900XTX)", "端口": 8080, "在线": _port_open(8080)},
        {"名称": "PaddleOCR (V100)", "端口": 8118, "在线": _port_open(8118)},
        {"名称": "OCR-multi (V100)", "端口": 8119, "在线": _port_open(8119)},
        {"名称": "bge-m3 嵌入 (7900XTX)", "端口": 8890, "在线": _port_open(8890)},
        {"名称": "PostgreSQL", "端口": 5432, "在线": _port_open(5432)},
    ]
    workers = [
        {"名称": ".12 省份抓取", "进程数": _pgrep(r"crawl_mp\.py run")},
        {"名称": ".12 流水线 worker", "进程数": _pgrep(r"run_loop\.sh")},
        {"名称": ".27 数据库隧道", "进程数": _pgrep(r"tunnel\.sh")},
    ]

    return {
        "更新时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "资产": assets,
        "省份": provinces,
        "队列": queues,
        "小时吞吐": rate,
        "服务": services,
        "worker": workers,
        "日志": [{"时间": a, "阶段": b, "内容": c} for a, b, c in (logs or [])],
    }


@bp.route("/overview", methods=["GET"])
@login_required
def overview():
    now = time.time()
    if _cache["data"] and now - _cache["ts"] < CACHE_SEC:
        return jsonify({"ok": True, "data": _cache["data"], "cached": True})
    try:
        data = collect()
    except Exception as e:
        return jsonify({"ok": False, "error": f"采集失败：{e}"}), 500
    _cache["ts"] = now
    _cache["data"] = data
    return jsonify({"ok": True, "data": data, "cached": False})
