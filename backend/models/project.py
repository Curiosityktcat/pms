from . import db


class Project(db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(50), unique=True)
    name = db.Column(db.String(200), nullable=False)
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

    def to_dict(self):
        return {
            "id": self.id,
            "number": self.number or "",
            "name": self.name,
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
        }
