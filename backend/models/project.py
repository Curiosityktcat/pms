from . import db

_CN_NUMS = ['', '一', '二', '三', '四', '五', '六', '七', '八', '九', '十']


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(200), nullable=False)
    round = db.Column(db.Integer, default=1)
    amount = db.Column(db.Float)
    line = db.Column(db.String(2))
    method = db.Column(db.String(30), default="")
    demand_dept = db.Column(db.String(100), default="")
    manage_dept = db.Column(db.String(100), default="")
    agency_code = db.Column(db.String(10), default="")
    officer = db.Column(db.String(50), default="")
    content = db.Column(db.Text, default="")
    bid_time = db.Column(db.String(50), default="")
    status = db.Column(db.String(20), default="立项")
    supervisor = db.Column(db.String(100), default="")
    representative = db.Column(db.String(200), default="")
    created_by = db.Column(db.String(100), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")
    is_draft = db.Column(db.Integer, default=0)
    can_open = db.Column(db.String(10), default="")
    bid_note = db.Column(db.Text, default="")
    category = db.Column(db.String(10), default="")
    year = db.Column(db.String(10), default="")
    is_deleted = db.Column(db.Integer, default=0)
    deleted_at = db.Column(db.String(30), default="")
    # 模块5 采购文件编制：两步确认（采购需求确认 / 采购文件确认）
    demand_confirmed = db.Column(db.Integer, default=0)
    demand_confirmed_by = db.Column(db.String(100), default="")
    demand_confirmed_at = db.Column(db.String(30), default="")
    doc_confirmed = db.Column(db.Integer, default=0)
    doc_confirmed_by = db.Column(db.String(100), default="")
    doc_confirmed_at = db.Column(db.String(30), default="")

    def to_dict(self):
        r = self.round or 1
        if r <= 1:
            display_name = self.name
        else:
            cn = _CN_NUMS[r] if r < len(_CN_NUMS) else str(r)
            display_name = f"{self.name}（第{cn}次）"
        return {
            "id": self.id,
            "number": self.number or "",
            "name": self.name,
            "round": r,
            "display_name": display_name,
            "amount": self.amount,
            "line": self.line or "",
            "method": self.method or "",
            "demand_dept": self.demand_dept or "",
            "manage_dept": self.manage_dept or "",
            "agency_code": self.agency_code or "",
            "officer": self.officer or "",
            "content": self.content or "",
            "bid_time": self.bid_time or "",
            "status": self.status or "",
            "supervisor": self.supervisor or "",
            "representative": self.representative or "",
            "created_by": self.created_by or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
            "is_draft": bool(self.is_draft),
            "can_open": self.can_open or "",
            "bid_note": self.bid_note or "",
            "category": self.category or "",
            "year": self.year or "",
            "is_deleted": bool(self.is_deleted),
            "deleted_at": self.deleted_at or "",
            "demand_confirmed": bool(self.demand_confirmed),
            "demand_confirmed_by": self.demand_confirmed_by or "",
            "demand_confirmed_at": self.demand_confirmed_at or "",
            "doc_confirmed": bool(self.doc_confirmed),
            "doc_confirmed_by": self.doc_confirmed_by or "",
            "doc_confirmed_at": self.doc_confirmed_at or "",
        }
