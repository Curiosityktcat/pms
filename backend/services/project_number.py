# -*- coding: utf-8 -*-
"""项目编号解析：从编号里读出「哪一年哪一月第几个」，供排序与展示。

黄新博的编号规则（2026-07-30 本人确认）：

    NJYYJX - HX - 260109
    └─┬──┘   └┬┘  └──┬─┘
      │       │      └── 26 年 01 月 第 09 个项目
      │       └───────── 代理机构（HX = 华询）
      └───────────────── 采购人 + 采购方式（NJYY = 内江医院，JX = 竞选）

所以**编号本身就带着时间**，比 id 或创建时间可靠——历史项目是后补进系统的，
id 完全不反映实际发生顺序（2024 年的项目 id 反而比 2026 年的大）。

除了这套主规则，库里还混着几种历史/外部编号，一并兼容：
    NJYYJX-CJ-2605001   PMS 自动生成的，序号 3 位（年月 + 3 位）
    ZZZB-2024-027       代理机构自己的编号，有年无月
    ZJNJ-2024164        同上，年份与序号连写
读不出年月的返回 ok=False，排序时统一沉到最后，不会假装它有时间。
"""
import re

# 主规则与 PMS 自动编号：结尾 6 位（年月+2位序号）或 7 位（年月+3位序号）
_YYMM = re.compile(r"(?:^|[-_])(\d{2})(\d{2})(\d{2,3})$")
# 代理机构编号：四位年份 + 分隔符 + 序号，或年份序号连写
_YYYY = re.compile(r"(?:^|[-_])(20\d{2})[-_]?(\d{1,4})$")


def parse(number):
    """把项目编号拆成 {year, month, seq, ok}。读不出时间的 ok=False。"""
    s = (number or "").strip()
    out = {"year": 0, "month": 0, "seq": 0, "ok": False}
    if not s:
        return out

    m = _YYMM.search(s)
    if m:
        yy, mm, seq = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mm <= 12:
            out.update(year=2000 + yy, month=mm, seq=seq, ok=True)
            return out

    m = _YYYY.search(s)
    if m:
        # 有年无月：月份记 0，排序时排在该年所有有月份的项目之后
        out.update(year=int(m.group(1)), month=0, seq=int(m.group(2)), ok=True)
        return out

    return out


def sort_key(number):
    """降序排列用的 key（越新越靠前）。

    读不出时间的排最后：ok 为 False 时首位给 0，其余项目首位给 1。
    """
    p = parse(number)
    return (1 if p["ok"] else 0, p["year"], p["month"], p["seq"])


def period(number):
    """`2026-01` 形式的所属期，给按月统计与筛选用；读不出返回空串。"""
    p = parse(number)
    if not p["ok"] or not p["month"]:
        return f"{p['year']}" if p["ok"] else ""
    return f"{p['year']:04d}-{p['month']:02d}"


def label(number):
    """给人看的「2026年1月第9个」；读不出返回空串。"""
    p = parse(number)
    if not p["ok"]:
        return ""
    if not p["month"]:
        return f"{p['year']}年第{p['seq']}个"
    return f"{p['year']}年{p['month']}月第{p['seq']}个"
