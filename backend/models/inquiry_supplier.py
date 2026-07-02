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
    # ── 评审字段（模块8 询议价评审填写） ──
    responded     = db.Column(db.Integer, default=0)        # 是否递交了响应（抓邮件/传文件自动置1，可手动改）
    qual_pass     = db.Column(db.String(10), default="")    # 资格性审查：''|通过|不通过
    conform_pass  = db.Column(db.String(10), default="")    # 符合性审查：''|通过|不通过
    final_price   = db.Column(db.String(100), default="")   # 最终价格（如"35133元"/"维持原价不变"）
    review_rank   = db.Column(db.String(20), default="")    # 评审排名（如"1"或"/"）
    fail_reason   = db.Column(db.String(200), default="")   # 无效原因（附件三无效供应商名单用）

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
