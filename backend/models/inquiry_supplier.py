from models import db


class InquirySupplier(db.Model):
    __tablename__ = "inquiry_suppliers"
    id            = db.Column(db.Integer, primary_key=True)
    inquiry_id    = db.Column(db.Integer, db.ForeignKey("inquiry_letters.id"), nullable=False)
    supplier_name = db.Column(db.String(200), default="")
    contact_name  = db.Column(db.String(50), default="")
    contact_phone = db.Column(db.String(30), default="")
    email         = db.Column(db.String(200), default="")
    sent_at       = db.Column(db.String(30), default="")    # 发送时间
    sent_by       = db.Column(db.String(50), default="")
    quote_amount  = db.Column(db.Float, nullable=True)      # 报价金额
    quote_date    = db.Column(db.String(30), default="")    # 报价日期
    quote_note    = db.Column(db.Text, default="")          # 回复备注
    is_selected   = db.Column(db.Integer, default=0)        # 是否成交

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
