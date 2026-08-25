# -*- coding: utf-8 -*-
"""把被串位写坏的标的数据还原。

坏法（前端按列下标取值，表头却少一列「采购品目」，整体左移一格）：
    catalog ← 用户填的「标的名称」
    name    ← 用户填的「数量」
    qty     ← 用户填的「单位」
    unit    ← 用户填的「单价/金额」
还原就是右移回去。只处理**明显串位**的行——catalog 有值且 name 是纯数字，
这是串位的特征（品目不会是纯数字，标的名称也不会）。拿不准的一律不动。

同一批标的还被重复存了两遍（saveTable 把顶层块的标的当成「别的包」并了进来），
按 (包号, 标的名称, 单价) 去重。
"""
import json
import os
import sqlite3
import sys

DB = os.environ.get("PMS_DB_PATH", "/home/huangxb/pms/pms.test.db")


def looks_shifted(it):
    """串位特征：品目有值、标的名称却是纯数字、且数量为空。"""
    catalog = str(it.get("catalog") or "").strip()
    name = str(it.get("name") or "").strip()
    qty = str(it.get("qty") or "").strip()
    return bool(catalog) and name.replace(".", "").isdigit() and qty == ""


def unshift(it):
    """右移一格还原：品目位上的其实是标的名称，名称位上的是数量，单位位上的是金额。"""
    return {
        "package_no": it.get("package_no") or "1",
        "no": it.get("no") or "",
        "catalog": "",                                  # 原来就没这一列，留空待填
        "name": str(it.get("catalog") or ""),
        "qty": it.get("name") or "",
        "unit": it.get("qty") or "",
        "unit_price": it.get("unit") or "",
        "amount": it.get("amount") or "",
        "energy": "", "energy_reason": "", "eco": "", "eco_reason": "",
        "import_ok": "", "industry": it.get("industry") or "",
    }


def main():
    apply = "--apply" in sys.argv
    conn = sqlite3.connect(DB)
    rows = list(conn.execute(
        "select id, project_name, items_json from procurement_demands"))
    touched = 0
    for did, pname, raw in rows:
        try:
            items = json.loads(raw or "[]")
        except Exception:
            continue
        if not isinstance(items, list) or not items:
            continue
        shifted = [x for x in items if isinstance(x, dict) and looks_shifted(x)]
        if not shifted:
            continue
        fixed = [unshift(x) if looks_shifted(x) else x for x in items]
        # 去重：同一包里 标的名称+单价 相同的只留一条（重复存两遍的那批）
        seen = set()
        deduped = []
        for x in fixed:
            key = (str(x.get("package_no")), str(x.get("name")), str(x.get("unit_price")))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(x)
        # 二次串位留下的空壳行：没有标的名称，品目位上只剩个数字（原来是序号/数量）。
        # 品目不会是纯数字，这种行没有任何可还原的信息，直接丢掉。
        def is_junk(x):
            name = str(x.get("name") or "").strip()
            catalog = str(x.get("catalog") or "").strip()
            if name:
                return False
            return not catalog or catalog.replace(".", "").isdigit()

        deduped = [x for x in deduped if not is_junk(x)]
        for i, x in enumerate(deduped, 1):
            x["no"] = str(i)
        print("需求 %s「%s」：%d 条 → 还原 %d 条串位，去重后 %d 条"
              % (did, pname, len(items), len(shifted), len(deduped)))
        for x in deduped:
            print("    名称=%-12s 数量=%-6s 单位=%-6s 单价=%s"
                  % (x.get("name"), x.get("qty"), x.get("unit"), x.get("unit_price")))
        touched += 1
        if apply:
            conn.execute("update procurement_demands set items_json=? where id=?",
                         (json.dumps(deduped, ensure_ascii=False), did))
    if apply:
        conn.commit()
        print("\n已修复 %d 条需求" % touched)
    else:
        print("\n这是预演（%d 条需求受影响）。加 --apply 才真写。" % touched)


if __name__ == "__main__":
    main()
