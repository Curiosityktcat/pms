#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目编号自动生成（最终版：按"是否走代理"定 XJ/JX）

判定规则：
  采购方式 + 金额 → 是否走代理 → 编号 + 流程线
  - 议价：不走代理
  - 询价：不走代理
  - 竞选：走代理
  - 招单价(挂网耗材)：等同≥5万竞选，走代理
  - 单一来源：由参数 sole_use_agency 决定走不走

  走代理  → NJYYJX-{代理缩写}-{YYMM}{seq3}，流程线 C
  不走代理 → NJYYXJ-{YYMM}{seq3}，流程线：<2万=A，2~5万=B，其它(如单一来源≥5万不走代理)=B
"""
import sqlite3, datetime, os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms.db")

# 采购方式常量
M_YIJIA = "院内议价"
M_XUNJIA = "院内询价"
M_JINGXUAN = "院内竞选"
M_SOLE = "院内单一来源采购"
M_ZHAODANJIA = "招单价"   # 表单里作为金额类型，方式仍归竞选


def decide(method, amount=None, is_unit_price=False, sole_use_agency=None):
    """
    返回 (use_agency: bool, line: 'A'/'B'/'C')
    method: 采购方式
    amount: 金额(元)，招单价时可为 None
    is_unit_price: 是否招单价(挂网耗材)
    sole_use_agency: 单一来源时是否走代理(True/False)，其它方式忽略
    """
    if is_unit_price:
        return True, "C"                      # 招单价等同≥5万竞选
    if method == M_JINGXUAN:
        return True, "C"
    if method == M_YIJIA:
        return False, "A"
    if method == M_XUNJIA:
        return False, "B"
    if method == M_SOLE:
        if sole_use_agency:
            return True, "C"
        else:
            # 单一来源不走代理：按金额给个线，≥5万也归 B（特例）
            if amount is not None and amount < 20000:
                return False, "A"
            return False, "B"
    # 兜底：按金额
    if amount is None:
        return True, "C"
    if amount < 20000:
        return False, "A"
    if amount < 50000:
        return False, "B"
    return True, "C"


def gen_number(conn, use_agency, agency_code=None, when=None):
    """根据是否走代理生成编号。走代理需 agency_code。"""
    now = when or datetime.datetime.now()
    ym = now.strftime("%y%m")
    c = conn.cursor()
    kind = "JX" if use_agency else "XJ"
    if use_agency and not agency_code:
        raise ValueError("走代理机构的项目必须指定代理机构")
    c.execute("INSERT OR IGNORE INTO number_seq(kind,ym,seq) VALUES(?,?,0)", (kind, ym))
    c.execute("UPDATE number_seq SET seq=seq+1 WHERE kind=? AND ym=?", (kind, ym))
    seq = c.execute("SELECT seq FROM number_seq WHERE kind=? AND ym=?", (kind, ym)).fetchone()[0]
    if use_agency:
        return f"NJYYJX-{agency_code}-{ym}{seq:03d}"
    return f"NJYYXJ-{ym}{seq:03d}"


# ---------- 自测 ----------
if __name__ == "__main__":
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE number_seq(kind TEXT,ym TEXT,seq INTEGER DEFAULT 0,PRIMARY KEY(kind,ym))")
    fixed = datetime.datetime(2026, 5, 15)
    cases = [
        ("院内议价", 15000, False, None, None, "刀片"),
        ("院内询价", 30000, False, None, None, "某设备"),
        ("院内竞选", 100000, False, "CJ", None, "颅骨夹"),
        ("院内竞选", None, True, "HX", None, "可吸收耗材(招单价)"),
        ("院内单一来源采购", 80000, False, "SJ", True, "单一来源-走代理"),
        ("院内单一来源采购", 80000, False, None, False, "单一来源-不走代理"),
        ("院内议价", 8000, False, None, None, "又一个议价"),
    ]
    print("模拟26年5月：")
    for method, amt, unit, code, sole, desc in cases:
        ua, line = decide(method, amt, unit, sole)
        num = gen_number(conn, ua, code if ua else None, fixed)
        amt_show = "招单价" if unit else amt
        print(f"  {desc:<22} 方式={method:<10} 金额={str(amt_show):<8} 走代理={ua} -> {num} (线{line})")
    conn.close()
