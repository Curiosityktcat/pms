from models import db


class RoundPackage(db.Model):
    """轮-包关系：某一轮里参与的包，以及该包在本轮的评审结果。

    采购结果确认时写入 result：成交→该包退出循环去签合同；废标→进入下一轮。
    """
    __tablename__ = "round_packages"

    id         = db.Column(db.Integer, primary_key=True)
    round_id   = db.Column(db.Integer, db.ForeignKey("procurement_rounds.id"), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey("packages.id"), nullable=False)
    result     = db.Column(db.String(10), default="待定")   # 待定|成交|废标
    winner     = db.Column(db.String(200), default="")
    win_amount = db.Column(db.Float, default=0)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
