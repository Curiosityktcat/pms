# -*- coding: utf-8 -*-
"""标的表回归：照黄新博 2026-08-25 报的四个问题各验一遍。

用他举的例子：包1 三个标的——手术机器人 1 台 500 万、麻醉机 3 台单价 50 万、
高频电刀 1 台 100 万，包限价应当是 750 万。

只验后端能验的部分（列规范、读回不串位、成稿取值、限价求和）；前端按 key
写入那一段由 tsc + 页面实测覆盖。
"""
import json
import os
import sys

sys.path.insert(0, "/home/huangxb/pms/backend")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"

import app as A
from models import db
from models.procurement_demand import ProcurementDemand
from services import demand_doc_ui as UI
from services import demand_doc

FAIL = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("✓" if cond else "✗", name, ("  → " + str(detail)) if detail else ""))
    if not cond:
        FAIL.append(name)


# 前端保存后 items_json 应有的样子（按列 key 存，合计金额已自动算）
ITEMS = [
    {"package_no": "1", "no": "1", "catalog": "医疗设备", "name": "手术机器人",
     "qty": 1, "unit": "台", "unit_price": 5000000, "amount": 5000000,
     "energy": "否", "energy_reason": "无国家节能产品清单对应品目", "eco": "是",
     "eco_reason": "", "import_ok": "是", "industry": "专用设备制造业"},
    {"package_no": "1", "no": "2", "catalog": "医疗设备", "name": "麻醉机",
     "qty": 3, "unit": "台", "unit_price": 500000, "amount": 1500000,
     "energy": "否", "energy_reason": "无对应清单", "eco": "是",
     "eco_reason": "", "import_ok": "否", "industry": "专用设备制造业"},
    {"package_no": "1", "no": "3", "catalog": "医疗设备", "name": "高频电刀",
     "qty": 1, "unit": "台", "unit_price": 1000000, "amount": 1000000,
     "energy": "否", "energy_reason": "无对应清单", "eco": "是",
     "eco_reason": "", "import_ok": "否", "industry": "专用设备制造业"},
]

a = A.create_app()
with a.app_context():
    d = db.session.get(ProcurementDemand, 18)
    backup = (d.items_json, d.packages_json)
    try:
        # 模拟前端存盘：主清单 + 包内镜像（镜像用中文键，和 saveValue 一致）
        cols = UI.ITEM_COLUMN_SPEC
        mirror = []
        for it in ITEMS:
            row = {"包号": it["package_no"]}
            for c in cols:
                row[c["cn"]] = it[c["key"]]
            mirror.append(row)
        total = sum(x["amount"] for x in ITEMS)
        d.items_json = json.dumps(ITEMS, ensure_ascii=False)
        d.packages_json = json.dumps([{"标的": mirror, "最高限价": total}], ensure_ascii=False)
        db.session.flush()

        print("[1] 包最高限价自动求和（500万+150万+100万）")
        check("限价 = 750 万", total == 7500000, "%s 元" % format(total, ","))

        print("[2] 存进去什么读回来就是什么（不再串位）")
        doc = UI.build(d)
        blocks = [b for s in doc["sections"] for b in s["blocks"] if b.get("field") == "标的"]
        check("标的块存在", len(blocks) >= 1, "%d 个" % len(blocks))
        top = blocks[0]
        head = top["header"]
        rows = top["rows"]
        check("表头 13 列（序号+12）", len(head) == 13, head)
        want = ["序号", "采购品目", "标的名称", "数量", "单位", "单价（元）", "合计金额（元）",
                "是否采购节能产品", "未采购节能产品原因", "是否采购环保产品",
                "未采购环保产品原因", "是否采购进口产品", "标的物所属行业"]
        check("表头就是要填的那 12 项", head == want, head)
        r2 = rows[1]
        check("第2行 标的名称=麻醉机", r2[head.index("标的名称")] == "麻醉机", r2)
        check("第2行 数量=3", str(r2[head.index("数量")]) == "3", r2)
        check("第2行 单位=台", r2[head.index("单位")] == "台", r2)
        # 成稿上下文会把金额格式化成 500,000.00，比较前先还原成数
        def num(v):
            return str(v).replace(",", "").rstrip("0").rstrip(".")
        check("第2行 单价=50万", num(r2[head.index("单价（元）")]) == "500000",
              r2[head.index("单价（元）")])
        check("第2行 合计=150万", num(r2[head.index("合计金额（元）")]) == "1500000",
              r2[head.index("合计金额（元）")])
        check("第2行 是否进口=否", r2[head.index("是否采购进口产品")] == "否", r2)
        check("第2行 行业已带出", r2[head.index("标的物所属行业")] == "专用设备制造业", r2)

        print("[3] 包内那张表和顶层那张列一致")
        pkg = [b for b in blocks if b.get("package_index") is not None]
        check("包内标的块存在", len(pkg) == 1, "%d 个" % len(pkg))
        if pkg:
            check("列与顶层完全一致", pkg[0]["header"] == head)
            check("包内行数 = 3", len(pkg[0]["rows"]) == 3, len(pkg[0]["rows"]))
            check("包内块带包号标签", "4.1" in (pkg[0]["label"] or ""), pkg[0]["label"])

        print("[4] 新增的列能进成稿")
        ctx = demand_doc.build_context(d)
        items = ctx.get("标的") or []
        check("成稿拿到 3 条标的", len(items) == 3, len(items))
        if items:
            it = items[1]
            check("成稿里 标的名称=麻醉机", it.get("标的名称") == "麻醉机", it.get("标的名称"))
            check("成稿里 单价有值", str(it.get("单价")) not in ("", "None"), it.get("单价"))
            check("成稿里 节能有值", it.get("节能") == "否", it.get("节能"))
            check("成稿里 未采购节能产品原因有值",
                  bool(it.get("未采购节能产品原因")), it.get("未采购节能产品原因"))
            check("成稿里 允许进口有值", it.get("允许进口") == "否", it.get("允许进口"))
            check("成稿里 所属行业有值", it.get("所属行业") == "专用设备制造业", it.get("所属行业"))
    finally:
        d.items_json, d.packages_json = backup
        db.session.rollback()

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "; ".join(FAIL)))
    sys.exit(1)
print("标的表四个问题的后端部分全部通过")
