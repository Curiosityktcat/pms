# -*- coding: utf-8 -*-
"""采购需求模板库：把填好的需求存成模板，别人可以复用。

黄新博 2026-08-19 ⑩ 的第 1 条：「我们很多项目都属于同一类型，大多数的内容都一样，
十一个部分的第三、六、七、八、九、十、十一部分都差不多。我需要能够有编辑模板的地方，
在已立项的界面后加一个模板，每个经办人可以让其他人 COPY 过去，或者是授权使用。」

存的不是 Word 文件，而是**一份填好的需求信息**（含分包）。用的时候拷进新需求里，
再改差异的那几项——和「复制上一个包」是同一个道理，只是跨项目。
"""
from models import db


class DemandTemplate(db.Model):
    __tablename__ = "demand_templates"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), default="")             # 模板名，如「医用耗材类·院内竞选」
    note = db.Column(db.Text, default="")                    # 什么时候用它
    demand_type = db.Column(db.String(20), default="gov")    # 适用的需求类型

    # 存哪些部分：默认第三、六~十一部分（他点名的那几个）
    sections_json = db.Column(db.Text, default="[]")
    # 模板内容：{字段名: 值} + packages（分包整份）
    data_json = db.Column(db.Text, default="{}")

    # 谁的模板。owner 之外的人要用，得 owner 授权或把模板设成公开
    owner = db.Column(db.String(50), index=True, default="")
    shared = db.Column(db.Integer, default=0)                # 1=全采购部可用
    shared_with = db.Column(db.Text, default="")             # 逗号分隔的被授权人姓名

    use_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def can_use(self, display_name, is_admin=False):
        """谁能用这份模板。"""
        if is_admin or self.owner == display_name or self.shared:
            return True
        names = {x.strip() for x in (self.shared_with or "").split(",") if x.strip()}
        return display_name in names

    def can_edit(self, display_name, is_admin=False):
        """只有主人（和管理员）能改和删——别人拿去用可以，改不了。"""
        return is_admin or self.owner == display_name

    def to_dict(self, me="", is_admin=False):
        import json
        try:
            sections = json.loads(self.sections_json or "[]")
        except Exception:                                    # noqa: BLE001
            sections = []
        return {
            "id": self.id, "name": self.name or "", "note": self.note or "",
            "demand_type": self.demand_type or "", "sections": sections,
            "owner": self.owner or "", "shared": bool(self.shared),
            "shared_with": [x.strip() for x in (self.shared_with or "").split(",") if x.strip()],
            "use_count": self.use_count or 0,
            "created_at": self.created_at or "", "updated_at": self.updated_at or "",
            "can_use": self.can_use(me, is_admin),
            "can_edit": self.can_edit(me, is_admin),
        }
