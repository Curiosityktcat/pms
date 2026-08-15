"""归口科室字典。

为什么要有别名：同一个科室会改名（设备科 → 医学装备部），历史项目里留的是旧名，
计划池 2026 表头留的还是旧名，而新项目写的是新名。如果按名字直接过滤，科室账号
登进来只能看到改名前的那一半项目。别名把「一个科室的所有曾用名」收进一个 code，
过滤时按 code 展开成名字集合去匹配——这样既不用改历史数据（110 行 manage_dept
改名是不可逆的），以后再改名也只是往 aliases 里加一个词。
"""
from datetime import datetime

from models import db


def _split(s):
    """别名串 → 名字列表。顿号/中文逗号/英文逗号/斜杠都当分隔符（人工维护容易混用）。"""
    if not s:
        return []
    out = []
    for part in str(s).replace("、", ",").replace("，", ",").replace("/", ",").split(","):
        part = part.strip()
        if part:
            out.append(part)
    return out


class Dept(db.Model):
    __tablename__ = "depts"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)   # 科室码，如 SBK
    name = db.Column(db.String(50), nullable=False)                # 现用名（展示用）
    aliases = db.Column(db.Text, default="")                       # 曾用名/别名，逗号分隔
    category = db.Column(db.String(20), default="")                # 归口/需求/实施/职能/监督/法务，可多值
    # 行后 / 临床医技。依据《2026-8-15 人员和权限设计》：所有科室都是需求科室，
    # 所有行后科室都是归口管理科室，**唯独采购部不是**（采管分离，岗位不兼容）。
    dept_type = db.Column(db.String(20), default="")
    head_name = db.Column(db.String(50), default="")               # 科室主要负责人
    active = db.Column(db.Integer, default=1)
    sort_no = db.Column(db.Integer, default=0)
    note = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def all_names(self):
        """本科室的全部名字（现用名 + 曾用名），用于匹配项目表里的科室字段。"""
        names = [self.name] + _split(self.aliases)
        seen, out = set(), []
        for n in names:
            if n and n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "aliases": _split(self.aliases),
            "category": self.category or "",
            "dept_type": self.dept_type or "",
            "head_name": self.head_name or "",
            "is_manage_dept": bool((self.dept_type or "") == "行后" and self.code != "CGB"),
            "active": self.active,
            "sort_no": self.sort_no or 0,
            "note": self.note or "",
        }
