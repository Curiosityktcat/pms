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
    # 草稿|待确认|已确认|已驳回|不确认
    status         = db.Column(db.String(10), default="草稿")

    # ── 驳回：编制有误，打回代理机构改单据（结果本身不变）──────────────
    reject_reason      = db.Column(db.Text, default="")
    reject_count       = db.Column(db.Integer, default=0)
    rejected_by        = db.Column(db.String(50), default="")
    rejected_at        = db.Column(db.String(30), default="")

    # ── 不确认：采购人不认可评审委员会给出的结果本身 ───────────────────
    # 与驳回的区别：评审已完成，结果无法"改回来"，只能由代理机构复核后
    # 给出处置（维持原结果 / 废标 / 部分废标 / 顺延候选人）再推送确认。
    not_confirm_reason = db.Column(db.Text, default="")
    not_confirm_count  = db.Column(db.Integer, default=0)
    not_confirmed_by   = db.Column(db.String(50), default="")
    not_confirmed_at   = db.Column(db.String(30), default="")
    recheck_handling   = db.Column(db.String(20), default="")  # 维持原结果|废标|部分废标|顺延候选人
    recheck_note       = db.Column(db.Text, default="")
    recheck_by         = db.Column(db.String(50), default="")
    recheck_at         = db.Column(db.String(30), default="")
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
