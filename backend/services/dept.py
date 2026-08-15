"""归口科室字典的读写与播种。

口径说明（与 services/project.list_projects 保持一致）：
  · 一个科室「相关的项目」= 归口科室(manage_dept) 命中 ∪ 需求科室(demand_dept) 命中。
    归口是它管的，需求是它提的，两种身份科室都该看得见。
  · 匹配用名字集合（现用名 + 曾用名），不用 code —— 项目表里存的是名字。
"""
from models import db
from models.dept import Dept, _split

# 播种表：(code, 现用名, 曾用名, 分类, 备注)
# 曾用名只写有实据的。拿不准的宁可分成两条，也不要错合——合错了会让 A 科室看见 B 科室的项目。
SEED_DEPTS = [
    ("SBK",  "医学装备部", "设备科", "归口",
     "设备科为曾用名：2024–2025 年项目写设备科，2025 年起写医学装备部，2026 计划池表头仍写设备科。待人工确认。"),
    ("BWK",  "保卫科", "", "归口", ""),
    ("JJK",  "基建科", "", "归口", ""),
    ("KJK",  "科教科", "", "归口", ""),
    ("GGWSK", "公共卫生科", "", "归口", ""),
    ("YJK",  "药剂科", "", "归口", ""),
    ("RSK",  "人事科", "", "归口", ""),
    ("DB",   "党办", "", "归口", ""),
    ("TW",   "团委", "", "归口", ""),
    ("SJK",  "审计科", "", "归口", ""),
    ("XCK",  "宣传科", "", "归口",
     "项目表另有「宣传统战社工部（文明办）」1 个项目，疑似同一科室改名，未合并，待人工确认。"),
    ("FWB",  "法务部", "", "归口", ""),
    ("YBK",  "预保科", "", "归口", ""),
    ("ZWK",  "总务科", "", "归口", ""),
    ("ZKB",  "质控办", "", "归口", ""),
    ("YWK",  "医务科", "", "归口",
     "项目表另有「医务部」，疑似同一科室，未合并，待人工确认。"),
    ("YB",   "院办", "", "归口", ""),
    ("JYK",  "检验科", "", "归口", ""),
]


def seed_depts():
    """幂等播种：只补不覆盖。已存在的 code 不动（人工改过的名字/别名要保住）。"""
    existing = {d.code for d in db.session.execute(db.select(Dept)).scalars()}
    added = 0
    for i, (code, name, aliases, category, note) in enumerate(SEED_DEPTS):
        if code in existing:
            continue
        db.session.add(Dept(code=code, name=name, aliases=aliases,
                            category=category, sort_no=i, note=note, active=1))
        added += 1
    if added:
        db.session.commit()
    return added


def list_depts(active_only=True):
    stmt = db.select(Dept)
    if active_only:
        stmt = stmt.where(Dept.active == 1)
    return list(db.session.execute(stmt.order_by(Dept.sort_no, Dept.id)).scalars())


def get_dept(code):
    if not code:
        return None
    return db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one_or_none()


def dept_names(code):
    """科室码 → 用于匹配项目表的名字集合。找不到科室时返回空列表（= 什么都看不到）。

    返回空列表是有意的：宁可让配错科室码的账号看不到任何项目，也不能让它看到全部。
    """
    d = get_dept(code)
    return d.all_names() if d else []


def canon_code(name):
    """项目表里的科室名 → 科室码。匹配不上返回 None。"""
    if not name:
        return None
    name = str(name).strip()
    for d in list_depts(active_only=False):
        if name in d.all_names():
            return d.code
    return None


def dept_display(code):
    d = get_dept(code)
    return d.name if d else (code or "")
