#!/usr/bin/env python3
"""重跑四川政采库的 items / eval_results 解析（修正 Hermes 解析器列映射 bug）。

数据源 = notices.content_html（已完整入库），不重爬。
策略：解析进 items_new / eval_new 两张新表，跑完打印覆盖率，
最后用 rename 原子切换（旧表保留为 *_bak_<ts> 可回滚）。

在 .12 上跑： ~/ccgp_venv/bin/python ccgp_reparse.py
"""
import re
import sys
import time

import psycopg2
import psycopg2.extras
from bs4 import BeautifulSoup

PG = dict(host="127.0.0.1", port=5432, dbname="ccgp",
          user="ccgp", password="CcgpData2025")


def to_num(s):
    s = re.sub(r"[^\d.]", "", s or "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def find_tables(soup, must):
    """返回所有表头同时含 must 中全部关键词的表（多合同包→多张表，全要）。"""
    res = []
    for tb in soup.find_all("table"):
        trs = tb.find_all("tr")
        if not trs:
            continue
        header = [x.get_text(strip=True) for x in trs[0].find_all(["td", "th"])]
        if header and all(any(m in h for h in header) for m in must):
            res.append((tb, header))
    return res


def col(header, *names):
    for nm in names:
        for j, h in enumerate(header):
            if nm in h:
                return j
    return -1


def parse_items(html):
    soup = BeautifulSoup(html or "", "html.parser")
    out = []
    for tb, header in find_tables(soup, ["采购标的"]):
        c_code = col(header, "品目编号")
        c_name = col(header, "品目名称")
        c_subj = col(header, "采购标的", "标的")
        c_brand = col(header, "品牌")
        c_spec = col(header, "规格")
        c_qty = col(header, "数量")
        c_up = col(header, "单价")
        c_rp = col(header, "响应报价", "响应单价")  # 网站多为模板注释，通常取不到，属正常
        for tr in tb.find_all("tr")[1:]:
            cells = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]
            if not any(cells):
                continue

            def g(i):
                return cells[i] if 0 <= i < len(cells) else ""

            subj = g(c_subj)
            if not subj and not g(c_code):
                continue
            qraw = g(c_qty)
            m = re.match(r"\s*([\d.]+)\s*[（(]?\s*([^)）]*)", qraw)
            qty = (m.group(1) if m else qraw) or None
            unit = (m.group(2).strip() if m else "") or None
            out.append((
                g(c_code) or None, g(c_name) or None, subj or None,
                g(c_brand) or None, g(c_spec) or None, qty, unit,
                to_num(g(c_up)), to_num(g(c_rp)),
            ))
    return out


def parse_award(html):
    soup = BeautifulSoup(html or "", "html.parser")
    out = []
    for tb, header in find_tables(soup, ["供应商名称"]):
        c_sup = col(header, "供应商名称")
        c_addr = col(header, "供应商地址", "地址")
        c_amt = col(header, "中标（成交）金额", "中标", "成交", "金额")
        c_score = col(header, "评审总得分", "得分", "评分")
        for tr in tb.find_all("tr")[1:]:
            cells = [x.get_text(strip=True) for x in tr.find_all(["td", "th"])]

            def g(i):
                return cells[i] if 0 <= i < len(cells) else ""

            sup = g(c_sup)
            if not sup or "供应商" in sup:
                continue
            score = to_num(g(c_score))
            out.append((
                sup or None, g(c_addr) or None, to_num(g(c_amt)),
                score, (score is not None and score >= 100),  # is_full_score 粗判
                True,  # 中标公告里列出的供应商即中标人
            ))
    return out


def main():
    t0 = time.time()
    conn = psycopg2.connect(**PG)
    conn.autocommit = False
    cur = conn.cursor()

    print("[1/4] 建新表 items_new / eval_new")
    cur.execute("DROP TABLE IF EXISTS items_new")
    cur.execute("DROP TABLE IF EXISTS eval_new")
    cur.execute("""CREATE TABLE items_new(
        id bigserial primary key, notice_id text, plan_id text,
        catalog_code text, catalog_name text, subject text, brand text,
        spec text, quantity text, unit text,
        unit_price numeric, response_price numeric)""")
    cur.execute("""CREATE TABLE eval_new(
        id bigserial primary key, notice_id text, plan_id text,
        supplier text, supplier_addr text, amount numeric, score numeric,
        is_full_score boolean, is_winner boolean)""")
    conn.commit()

    print("[2/4] 流式读取 notices 并解析")
    read_conn = psycopg2.connect(**PG)  # 独立读连接，避免写连接 commit 失效游标
    rd = read_conn.cursor(name="notices_cur")  # 服务端游标，省内存
    rd.itersize = 2000
    rd.execute("""select id, plan_id, content_html from notices
                  where content_html is not null and length(content_html) > 200""")
    item_buf, eval_buf = [], []
    n = n_item = n_eval = 0
    for nid, pid, html in rd:
        n += 1
        for it in parse_items(html):
            item_buf.append((nid, pid, *it))
        for ev in parse_award(html):
            eval_buf.append((nid, pid, *ev))
        if len(item_buf) >= 5000:
            psycopg2.extras.execute_values(cur,
                "insert into items_new(notice_id,plan_id,catalog_code,catalog_name,"
                "subject,brand,spec,quantity,unit,unit_price,response_price) values %s",
                item_buf)
            n_item += len(item_buf); item_buf = []
        if len(eval_buf) >= 5000:
            psycopg2.extras.execute_values(cur,
                "insert into eval_new(notice_id,plan_id,supplier,supplier_addr,"
                "amount,score,is_full_score,is_winner) values %s", eval_buf)
            n_eval += len(eval_buf); eval_buf = []
        if n % 10000 == 0:
            conn.commit()
            print(f"   ...{n} 公告  items={n_item+len(item_buf)} eval={n_eval+len(eval_buf)}  {time.time()-t0:.0f}s")
    if item_buf:
        psycopg2.extras.execute_values(cur,
            "insert into items_new(notice_id,plan_id,catalog_code,catalog_name,"
            "subject,brand,spec,quantity,unit,unit_price,response_price) values %s", item_buf)
        n_item += len(item_buf)
    if eval_buf:
        psycopg2.extras.execute_values(cur,
            "insert into eval_new(notice_id,plan_id,supplier,supplier_addr,"
            "amount,score,is_full_score,is_winner) values %s", eval_buf)
        n_eval += len(eval_buf)
    rd.close()
    read_conn.close()
    conn.commit()
    print(f"   解析完成：{n} 公告 → items={n_item} eval={n_eval}  {time.time()-t0:.0f}s")

    print("[3/4] 覆盖率自检")
    for tbl, cols in [("items_new", ["catalog_name", "unit_price", "unit", "subject"]),
                      ("eval_new", ["supplier", "supplier_addr", "score", "amount"])]:
        cur.execute(f"select count(*) from {tbl}"); tot = cur.fetchone()[0]
        parts = []
        for cc in cols:
            cur.execute(f"select count(*) from {tbl} where {cc} is not null")
            parts.append(f"{cc}={cur.fetchone()[0]:,}")
        print(f"   {tbl}({tot:,}): " + "  ".join(parts))

    ts = time.strftime("%Y%m%d_%H%M%S")
    print(f"[4/4] 原子切换（旧表存为 *_bak_{ts}）")
    cur.execute(f"ALTER TABLE items RENAME TO items_bak_{ts}")
    cur.execute(f"ALTER TABLE eval_results RENAME TO eval_results_bak_{ts}")
    cur.execute("ALTER TABLE items_new RENAME TO items")
    cur.execute("ALTER TABLE eval_new RENAME TO eval_results")
    conn.commit()
    print(f"✓ 全部完成，用时 {time.time()-t0:.0f}s。旧表备份后缀 _bak_{ts}")
    conn.close()


if __name__ == "__main__":
    main()
