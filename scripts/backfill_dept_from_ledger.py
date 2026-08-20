# -*- coding: utf-8 -*-
"""从「黄新博 项目汇总.xlsx」台账把项目的归口/需求科室回填到 PMS。

只回填两个科室字段都空着的项目，按项目编号精确对上台账行，绝不覆盖已有值。

**归口和需求两列的处理不一样**：
  · 归口管理科室：台账里写的（设备科/科教科/基建科/保卫科/审计科/医学装备部）
    全都能在科室字典里认出来，直接写。
  · 需求科室：台账里是口语名（麻醉科/皮肤科/呼吸科/肝胆外科），字典里对应的是
    麻醉手术中心/皮肤美容科/呼吸与危重症医学科/普外科（肝胆胰脾）。**不猜**——
    认不出来的留空并列出来，等人确认。写个认不出的名字进去，结果还是没人认领。
"""
import os
import sqlite3
import sys

import openpyxl

DB = "/home/huangxb/pms/pms.db"
LEDGER = "/home/huangxb/files/PMS改造/黄新博 项目汇总.xlsx"


def dept_names(conn):
    """现用名 + 曾用名 → 现用名。项目表里存的是名字，写进去的值必须能被认出来。"""
    out = {}
    for name, aliases in conn.execute("select name, aliases from depts where active=1"):
        out[name] = name
        for a in (aliases or "").replace("、", ",").replace("，", ",").split(","):
            if a.strip():
                out[a.strip()] = a.strip()      # 曾用名照原样存，字典能认
    return out


def read_ledger():
    wb = openpyxl.load_workbook(LEDGER, read_only=True)
    rows = {}
    for ws in wb.worksheets:
        hdr = None
        for r in ws.iter_rows(values_only=True):
            vals = ["" if v is None else str(v).strip() for v in r]
            if hdr is None:
                if any(v == "项目编号" for v in vals):
                    hdr = {v: i for i, v in enumerate(vals)}
                continue
            gi = hdr.get("项目编号")
            if gi is None or gi >= len(vals) or not vals[gi]:
                continue
            get = lambda k: vals[hdr[k]] if k in hdr and hdr[k] < len(vals) else ""
            rows[vals[gi]] = (get("需求科室"), get("归口管理科室") or get("归口科室"), ws.title)
    return rows


def main():
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB)
    known = dept_names(conn)
    ledger = read_ledger()

    todo = []
    unresolved = []
    for pid, num, name in conn.execute(
            "select id, number, name from projects "
            "where (manage_dept is null or trim(manage_dept)='') "
            "  and (demand_dept is null or trim(demand_dept)='')"):
        num = (num or "").strip()
        if not num or num not in ledger:
            continue
        want_d, want_m, sheet = ledger[num]
        m = known.get(want_m, "")
        d = known.get(want_d, "")
        if not m and not d:
            continue
        if want_d and not d:
            unresolved.append((num, want_d))
        todo.append((pid, num, name, d, m, sheet))

    print("可回填 %d 条：" % len(todo))
    for _pid, num, name, d, m, sheet in todo:
        print("   %-18s %-34s 归口=%-10s 需求=%-10s [%s]"
              % (num, (name or "")[:34], m or "-", d or "(留空)", sheet))
    if unresolved:
        print()
        print("台账写了需求科室但字典认不出、故意留空的 %d 条：" % len(unresolved))
        for num, raw in unresolved:
            print("   %-18s 台账写的是「%s」" % (num, raw))

    if not apply:
        print()
        print("这是预演。加 --apply 才真写。")
        return

    for pid, _num, _name, d, m, _s in todo:
        conn.execute("update projects set manage_dept=?, demand_dept=? where id=?",
                     (m or "", d or "", pid))
    conn.commit()
    print()
    print("已回填 %d 条" % len(todo))


if __name__ == "__main__":
    main()
