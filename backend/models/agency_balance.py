from . import db


class AgencyBalance(db.Model):
    """代理机构 AI 用量余额（元）。按 agency_code 一对一。"""
    __tablename__ = "agency_balance"

    agency_code = db.Column(db.String(10), primary_key=True)
    balance = db.Column(db.Float, default=0)          # 当前余额（元）
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "agency_code": self.agency_code,
            "balance": round(self.balance or 0, 4),
            "updated_at": self.updated_at or "",
        }
