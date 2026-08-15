"""按《内江市第一人民医院采购管理内部控制制度》补齐科室字典并分类。

内控里的科室分工（第九～十五条）：
  归口  采购归口管理科室（=预算归口，各行政职能科室），负责需求编制、审查、验收、付款
  实施  采购部（组织实施采购、编制采购文件、组织评审、签合同、档案）
  职能  采购职能科室：财务科、运营管理部、资产管理组
  法务  法务部（需求/合同法律审核会签、争议处理）——同时也是归口科室之一
  监督  纪委办、审计科——审计科同时也是归口科室，所以 category 允许多值
  需求  临床/医技/行政各科室（名单未定，先不建，类别留着）

只新增/补类别，不删不改现有条目的 code。
"""
import sys
sys.path.insert(0, ".")

from app import create_app
from models import db
from models.dept import Dept

# code, 名称, 类别(可多值), 别名, 排序
SEED = [
    ("CGB",   "采购部",     "实施",      "采购管理部",         1),
    ("CWK",   "财务科",     "职能",      "财务部",            2),
    ("YYGLB", "运营管理部", "职能",      "运营部",            3),
    ("ZCGLZ", "资产管理组", "职能",      "资产管理科,资产科",  4),
    ("JWB",   "纪委办",     "监督",      "纪委办公室",         5),
    ("XZB",   "行政办",     "归口",      "行政办公室",         6),
    ("YGK",   "院感科",     "归口",      "医院感染管理科",     7),
    ("HLB",   "护理部",     "归口",      "",                  8),
    ("XXK",   "信息科",     "归口",      "信息中心",           9),
]

# 现有条目的类别订正：审计科两栖（既是归口科室，也是监督机构）
FIX = {
    "SJK": {"category": "归口,监督"},
    "FWB": {"category": "归口,法务"},
    "XCK": {"aliases": "宣传统战部,宣传统战社工部"},
}

app = create_app()
with app.app_context():
    added, fixed = [], []
    for code, name, cat, aliases, sort_no in SEED:
        row = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one_or_none()
        if row:
            if not row.category:
                row.category = cat
                fixed.append(f"{row.name}(补类别 {cat})")
            continue
        db.session.add(Dept(code=code, name=name, category=cat,
                            aliases=aliases, sort_no=100 + sort_no, active=1,
                            note="按采购管理内控制度补建"))
        added.append(f"{name}[{code}] 类别={cat}")
    for code, kw in FIX.items():
        row = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one_or_none()
        if not row:
            continue
        for k, v in kw.items():
            if (getattr(row, k) or "") != v:
                setattr(row, k, v)
                fixed.append(f"{row.name}.{k}={v}")
    db.session.commit()

    print("新增：", "；".join(added) or "无")
    print("订正：", "；".join(fixed) or "无")
    print("\n── 现有科室字典 ──")
    for d in db.session.execute(db.select(Dept).order_by(Dept.sort_no, Dept.id)).scalars():
        print(f"  {d.code:<7} {d.name:<8} 类别={d.category or '-':<8} 别名={d.aliases or '-'}")
