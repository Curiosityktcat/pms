#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把四川政采附件重下到干净的「按项目」结构（修 Hermes 散沙归档）。

只下三类（黄新博口径）：
  - 采购文件   category='采购文件'
  - 评审记录   category='中标公告' 且 文件名含 评审/评标/评分/评定
  - 合同附件   category='合同公告' 全部（合同要完整保留）
同时把每个项目的「公告正文 + 原链接」落一份 公告正文.txt。

数据全在库里（notices/attachments），源链接 attachments.source_url 实测仍有效，
故不重爬列表，直接从直链重下。curl 走系统网络栈，避开 .12 透明代理对 python
requests 并发的 hang。密码走 ~/.pgpass（不写进本文件）。可断点续传（已存在且非空则跳过）。

用法：
  python3 ccgp_redownload.py test        # 随机 20 个项目试跑
  python3 ccgp_redownload.py             # 全量
  python3 ccgp_redownload.py manifest     # 只生成各项目 公告正文.txt，不下附件
"""
import os
import re
import sys
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2

PG = dict(host="127.0.0.1", port=5432, dbname="ccgp", user="ccgp")  # 密码走 ~/.pgpass
OUT = os.path.expanduser("~/ccgp_clean")
WORKERS = 5

ATT_SQL = """
select a.id, a.notice_id, a.plan_id, a.category, a.filename, a.source_url,
       n.purchaser, n.title
from attachments a
join notices n on n.id = a.notice_id
where a.source_url like 'https://gpx%%'
  and ( a.category = '采购文件'
     or (a.category = '中标公告' and a.filename ~ '评审|评标|评分|评定')
     or a.category = '合同公告' )
"""

PICK_20 = ("select plan_id from notices where plan_id is not null "
           "group by plan_id order by random() limit 20")


def safe(s, n=120):
    return re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", (s or "").strip())[:n] or "未命名"


def classify(category, filename):
    if category == "采购文件":
        return "采购文件"
    if category == "合同公告":
        return "合同"
    return "评审记录"


def proj_dir(purchaser, title, plan_id, notice_id):
    proj = safe(title, 80) + "_" + (plan_id or notice_id or "x")[:8]
    return os.path.join(OUT, safe(purchaser or "未知采购人"), proj)


def build_path(r):
    aid, nid, pid, cat, fn, url, purchaser, title = r
    return os.path.join(proj_dir(purchaser, title, pid, nid),
                        classify(cat, fn), safe(fn, 120))


def download(r):
    aid = r[0]
    url = r[5]
    path = build_path(r)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return aid, path, os.path.getsize(path), "skip"
    rc = subprocess.run(
        ["curl", "-sk", "--max-time", "120", "-o", path, url],
        capture_output=True).returncode
    if rc != 0 or not os.path.exists(path):
        return aid, path, 0, "fail"
    sz = os.path.getsize(path)
    return aid, path, sz, ("ok" if sz > 0 else "empty")


def dump_manifests(cur, plan_ids=None):
    """每个项目落一份 公告正文.txt：标题 / 类型 / 原链接 / 正文。"""
    if plan_ids is not None:
        cur.execute("""
            select plan_id, purchaser, title, notice_type, notice_time,
                   win_company, amount, source_url, content
            from notices where plan_id = any(%s) order by plan_id, notice_time
        """, (plan_ids,))
    else:
        cur.execute("""
            select plan_id, purchaser, title, notice_type, notice_time,
                   win_company, amount, source_url, content
            from notices order by plan_id, notice_time
        """)
    cur_pid = None
    buf = []
    n = 0
    rows = cur.fetchall()

    def flush(pid, purchaser, title, buf):
        if not buf:
            return
        d = proj_dir(purchaser, title, pid, None)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "公告正文.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(buf))

    last = None
    for (pid, purchaser, title, ntype, ntime, win, amount, url, content) in rows:
        if pid != cur_pid:
            if last:
                flush(*last, buf)
                n += 1
            cur_pid = pid
            buf = []
            last = (pid, purchaser, title)
        buf.append(f"【{ntype}】{title}")
        buf.append(f"  公告时间: {ntime}   中标人: {win or '-'}   金额: {amount or '-'}")
        buf.append(f"  原链接: {url}")
        buf.append("  正文:")
        buf.append((content or "").strip())
        buf.append("\n" + "=" * 60 + "\n")
    if last:
        flush(*last, buf)
        n += 1
    print(f"  公告正文.txt 已生成 {n} 个项目")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    conn = psycopg2.connect(**PG)
    cur = conn.cursor()

    if mode == "manifest":
        dump_manifests(cur)
        return

    test_pids = None
    q = ATT_SQL
    if mode == "test":
        cur.execute(PICK_20)
        test_pids = [r[0] for r in cur.fetchall()]
        q = ATT_SQL + " and a.plan_id = any(%s)"
        cur.execute(q, (test_pids,))
    else:
        cur.execute(q)
    rows = cur.fetchall()
    total = len(rows)
    print(f"[{mode}] 待下载 {total} 个附件 -> {OUT}", flush=True)

    wconn = psycopg2.connect(**PG)
    wcur = wconn.cursor()
    ok = fail = done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(download, r) for r in rows]
        for fu in as_completed(futs):
            aid, path, sz, st = fu.result()
            done += 1
            if st in ("ok", "skip"):
                ok += 1
                wcur.execute(
                    "update attachments set rel_path=%s, downloaded=true, "
                    "size=%s where id=%s",
                    (os.path.relpath(path, OUT), sz, aid))
            else:
                fail += 1
            if done % 200 == 0:
                wconn.commit()
                print(f"  {done}/{total}  ok={ok} fail={fail}", flush=True)
    wconn.commit()
    print(f"[{mode}] 附件完成 ok={ok} fail={fail}", flush=True)

    # 顺带把这批项目的公告正文也落地
    dump_manifests(cur, test_pids)


if __name__ == "__main__":
    main()
