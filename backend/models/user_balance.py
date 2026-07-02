from . import db


class UserBalance(db.Model):
    """按人 AI 计费余额。每人初始 10 元免费额度；师芮/黄新博 无限不计费。
    扣费标准复用 services.billing（10 元/百万 token）。"""
    __tablename__ = "user_balances"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, index=True)
    display_name = db.Column(db.String(50), default="")
    balance = db.Column(db.Float, default=10.0)      # 当前余额（元），初始 10 免费
    recharged = db.Column(db.Float, default=0.0)     # 累计充值（元）
    spent = db.Column(db.Float, default=0.0)         # 累计消费（元）
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
