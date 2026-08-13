# -*- coding: utf-8 -*-
"""采购计划池：归口科室报上来的年度采购计划，是采购项目的「前身」。

与 Project 是两张表、两个生命周期（见《WPS小团队搬入PMS方案》）：
计划年初就有、一个科室上百条，其中只有一部分会真的立项；
立项后用 project_id 挂钩，一条计划最多对应一个采购项目。

各科室导出的列并不完全一致（设备科用「元」还带限价，其他科室用「万元」），
所以固定列只留公共部分，各科室多出来的列原样进 extra_json，不丢数据。
"""
from models import db

# 这几个状态说明这条计划不会走到采购部，列表默认不显示
NOT_PROCURED = ("已合并", "已集采", "延期合并", "已取消", "作废")


class ProcurementPlan(db.Model):
    __tablename__ = "procurement_plans"

    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.Integer, index=True, default=0)          # 计划年度
    dept = db.Column(db.String(60), index=True, default="")      # 归口科室
    demand_dept = db.Column(db.String(60), default="")           # 需求科室
    name = db.Column(db.String(300), default="")                 # 计划项目名称
    package_no = db.Column(db.String(200), default="")           # 项目名称及包号
    plan_number = db.Column(db.String(80), index=True, default="")  # 采购项目编号（立项后回填）

    org_form = db.Column(db.String(30), default="")              # 组织形式：自行采购/集中采购
    method = db.Column(db.String(30), default="")                # 采购方式：院内竞选/议价/询价
    deadline = db.Column(db.String(60), default="")              # 采购期限
    budget = db.Column(db.Float, default=0.0)                    # 预算（统一折算成元）
    price_limit = db.Column(db.Float, default=0.0)               # 限价（元）
    qty = db.Column(db.String(40), default="")
    unit = db.Column(db.String(20), default="")

    category = db.Column(db.String(40), index=True, default="")  # 分类
    category2 = db.Column(db.String(40), default="")             # 分类2
    demand_type = db.Column(db.String(60), default="")           # 需求类型
    status = db.Column(db.String(40), index=True, default="")    # 状态（含已合并/已集采等）
    note = db.Column(db.Text, default="")

    # 与正式采购项目的关联：只认人工点选或编号回填，不做名称自动匹配
    project_id = db.Column(db.Integer, index=True, nullable=True)
    linked_by = db.Column(db.String(50), default="")
    linked_at = db.Column(db.String(30), default="")

    source_file = db.Column(db.String(200), default="")          # 来自哪个导出文件
    source_row = db.Column(db.Integer, default=0)                # 原表第几行，便于回溯
    extra_json = db.Column(db.Text, default="{}")                # 该科室多出来的列

    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")
    created_by = db.Column(db.String(50), default="")

    def to_dict(self, project=None):
        import json
        try:
            extra = json.loads(self.extra_json or "{}")
        except Exception:
            extra = {}
        return {
            "id": self.id,
            "year": self.year or 0,
            "dept": self.dept or "",
            "demand_dept": self.demand_dept or "",
            "name": self.name or "",
            "package_no": self.package_no or "",
            "plan_number": self.plan_number or "",
            "org_form": self.org_form or "",
            "method": self.method or "",
            "deadline": self.deadline or "",
            "budget": self.budget or 0.0,
            "price_limit": self.price_limit or 0.0,
            "qty": self.qty or "",
            "unit": self.unit or "",
            "category": self.category or "",
            "category2": self.category2 or "",
            "demand_type": self.demand_type or "",
            "status": self.status or "",
            "note": self.note or "",
            "project_id": self.project_id,
            "project_number": (project.number if project else ""),
            "project_name": (project.name if project else ""),
            "project_status": (project.status if project else ""),
            "linked_by": self.linked_by or "",
            "linked_at": self.linked_at or "",
            "will_procure": (self.status or "") not in NOT_PROCURED,
            "source_file": self.source_file or "",
            "extra": extra,
        }


class ProcurementPlanAttachment(db.Model):
    """计划条目的附件（科室需求表、办公会决议、报价单等）。

    WPS 导出的附件文件名是「项目名_原文件名」，导入时按前缀归到对应计划；
    之后在 PMS 里还能继续拖拽上传、删除。
    """
    __tablename__ = "procurement_plan_attachments"

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, index=True)
    filename = db.Column(db.String(300), default="")     # 展示名
    path = db.Column(db.String(500), default="")         # 磁盘绝对路径
    size = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(50), default="")
    uploaded_at = db.Column(db.String(30), default="")
    source = db.Column(db.String(20), default="wps")     # wps=导入的 | upload=后来传的

    def to_dict(self):
        return {
            "id": self.id, "plan_id": self.plan_id,
            "filename": self.filename or "", "size": self.size or 0,
            "uploaded_by": self.uploaded_by or "", "uploaded_at": self.uploaded_at or "",
            "source": self.source or "",
            "ext": (self.filename or "").rsplit(".", 1)[-1].lower() if "." in (self.filename or "") else "",
        }
