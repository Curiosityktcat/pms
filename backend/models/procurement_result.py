from datetime import datetime
from models import db
import json

class ProcurementResult(db.Model):
    __tablename__ = "procurement_results"
    id             = db.Column(db.Integer, primary_key=True)
    project_id     = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    round_number   = db.Column(db.Integer, default=1)        # 第几次竞选
    bid_time       = db.Column(db.String(50), default="")    # 竞选时间
    agency_name    = db.Column(db.String(100), default="")   # 招标代理机构
    procurement_method = db.Column(db.String(20), default="院内竞选")
    # packages_json: JSON list，每包: {result:'成交'|'废标', winner:str, amount:float, amount_cn:str, note:str}
    packages_json  = db.Column(db.Text, default="[]")
    notes          = db.Column(db.Text, default="此结果为评审委员会评审结果")
    confirm_date   = db.Column(db.String(20), default="")    # 签章日期
    status         = db.Column(db.String(10), default="草稿") # 草稿|已确认
    created_by     = db.Column(db.String(50), default="")
    created_at     = db.Column(db.String(30), default="")
    updated_at     = db.Column(db.String(30), default="")

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        try:
            d["packages"] = json.loads(self.packages_json or "[]")
        except Exception:
            d["packages"] = []
        return d
