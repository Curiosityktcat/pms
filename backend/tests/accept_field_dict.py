"""字段字典引擎验收：条件锁定 / 级联子字段 / 选项携带固定值。

黄新博 2026-08-19 认可的方向：条件和联动放字段字典，Word 模板保持笨。
这个脚本验的就是「字典说了算」这件事本身。
"""
import sys
sys.path.insert(0, ".")
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from services import field_dict as fd

fields = fd.load()
check("① 字典读得到", len(fields) > 60, f"{len(fields)} 个字段")

# ═══ ① 3.1 只留分散采购 ═════════════════════════════════════════
f = next(x for x in fields if x["name"] == "采购组织形式")
check("① 3.1 只剩「分散采购」一个选项", fd.option_labels(f) == ["分散采购"],
      f"{fd.option_labels(f)}")
eff, meta = fd.resolve(fields, {"采购组织形式": "自行采购"})
check("① 填错了也会被锁回分散采购", eff["采购组织形式"] == "分散采购",
      f"{eff['采购组织形式']!r}")
check("① 界面上标成只读并说明理由", meta["采购组织形式"]["locked"],
      meta["采购组织形式"]["locked_reason"])

# ═══ ② 3.2 只留政采方式 ═════════════════════════════════════════
f = next(x for x in fields if x["name"] == "采购方式")
check("② 3.2 是政采的六种", set(fd.option_labels(f)) ==
      {"公开招标", "竞争性谈判", "竞争性磋商", "单一来源", "询价", "邀请招标"},
      f"{fd.option_labels(f)}")
_, meta = fd.resolve(fields, {})
check("② 自行采购那两栏不出现在这张表",
      not meta["预算采购方式"]["visible"] and not meta["采购方式2"]["visible"])

# ═══ ③ 货物锁「否」、服务给提示 ══════════════════════════════════
eff, meta = fd.resolve(fields, {"项目所属分类": "货物", "是否属于一签多年项目": "是"})
check("③ 货物类被锁成「否」", eff["是否属于一签多年项目"] == "否",
      f"填的是「是」→ {eff['是否属于一签多年项目']!r}")
check("③ 锁的时候说明了理由", "货物" in meta["是否属于一签多年项目"]["locked_reason"],
      meta["是否属于一签多年项目"]["locked_reason"])
eff, meta = fd.resolve(fields, {"项目所属分类": "服务", "是否属于一签多年项目": "是"})
check("③ 服务类不锁，填「是」就是「是」", eff["是否属于一签多年项目"] == "是")
check("③ 服务类给出提示", "服务期限超 1 年" in meta["是否属于一签多年项目"]["hint"],
      meta["是否属于一签多年项目"]["hint"][:28])

# ═══ ④ 分包 → 包数 ═════════════════════════════════════════════
eff, meta = fd.resolve(fields, {"采购包划分": "不分包采购", "包数": 5})
check("④ 不分包时包数锁成 1", eff["包数"] == 1, f"填了 5 → {eff['包数']}")
check("④ 包数标成只读", meta["包数"]["locked"], meta["包数"]["locked_reason"])
eff, meta = fd.resolve(fields, {"采购包划分": "分包采购", "包数": 3})
check("④ 分包时包数由人定", eff["包数"] == 3 and not meta["包数"]["locked"],
      f"包数={eff['包数']} 锁={meta['包数']['locked']}")

# ═══ ⑤ 中小企业政策级联 ═════════════════════════════════════════
_, meta = fd.resolve(fields, {"中小企业政策": "不专门面向中小企业采购"})
check("⑤ 选「不专门面向」时三个子项都不出现",
      not any(meta[k]["visible"] for k in ("面向的企业规模", "预留形式", "预留比例")))
check("⑤ 这时才出现「是否进行价格扣除」", meta["是否进行价格扣除"]["visible"])

_, meta = fd.resolve(fields, {"中小企业政策": "专门面向中小企业采购"})
check("⑤ 选「专门面向」时三个子项都出现",
      all(meta[k]["visible"] for k in ("面向的企业规模", "预留形式", "预留比例")))
check("⑤ 这时不再问价格扣除", not meta["是否进行价格扣除"]["visible"])

eff, meta = fd.resolve(fields, {"中小企业政策": "专门面向中小企业采购",
                                "预留形式": "专门采购包预留", "预留比例": 30})
check("⑤ 专门采购包预留 → 比例锁 100", eff["预留比例"] == 100, f"填了 30 → {eff['预留比例']}")
eff, _ = fd.resolve(fields, {"中小企业政策": "专门面向中小企业采购",
                             "预留形式": "要求分包", "预留比例": 30})
check("⑤ 其他预留形式比例由人填", eff["预留比例"] == 30)

# ═══ ⑨ 价格扣除：选项携带固定值 ═════════════════════════════════
base = {"中小企业政策": "不专门面向中小企业采购", "是否进行价格扣除": "是"}
for label, want in (("小微企业报价扣除", 20),
                    ("联合体小微份额≥30%", 6),
                    ("分包给小微份额≥30%", 6)):
    eff, meta = fd.resolve(fields, {**base, "价格扣除情形": label,
                                    "价格扣除比例": 99, "价格扣除评审标准": "我乱写的"})
    check(f"⑨ 选「{label}」→ 比例自动 {want}%", eff["价格扣除比例"] == want,
          f"填了 99 → {eff['价格扣除比例']}")
    check(f"⑨ 「{label}」的评审标准被写死",
          "评审价=响应报价×（1-C1）" in str(eff["价格扣除评审标准"])
          and "财库〔2020〕46号" in str(eff["价格扣除评审标准"]),
          f"{str(eff['价格扣除评审标准'])[:26]}…")
    check(f"⑨ 「{label}」比例与标准都标成只读",
          meta["价格扣除比例"]["locked"] and meta["价格扣除评审标准"]["locked"])

f = next(x for x in fields if x["name"] == "价格扣除情形")
check("⑨ 三种情形的原文都在字典里",
      all(len(o.get("text", "")) > 40 for o in f["options"]),
      f"{[len(o.get('text','')) for o in f['options']]} 字")

# ═══ 校验 ═══════════════════════════════════════════════════════
errs = fd.validate(fields, {"中小企业政策": "专门面向中小企业采购"})
check("⑥ 该填没填会报出来", any("面向的企业规模" in e for e in errs), f"{errs[:2]}")
errs = fd.validate(fields, {"中小企业政策": "不专门面向中小企业采购"})
check("⑥ 不显示的字段不算必填",
      not any("面向的企业规模" in e for e in errs), f"{errs[:2]}")
errs = fd.validate(fields, {"中小企业政策": "专门面向中小企业采购",
                            "面向的企业规模": "中小企业", "预留形式": "要求分包",
                            "预留比例": "123.456"})
check("⑥ 超范围的数字被拦", any("不能大于" in e for e in errs), f"{errs[:2]}")
errs = fd.validate(fields, {"采购方式": "院内竞选"})
check("⑥ 不在选项里的值被拦", any("不在选项里" in e for e in errs), f"{errs[:2]}")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
