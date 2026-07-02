from models import db


class Package(db.Model):
    """采购包（标段）。在 5.1 采购需求确认时按「包数量」生成，贯穿项目始终、中途不变。

    一个包恰好对应一份合同；中标后退出循环去签合同，废标则滚入下一轮。
    """
    __tablename__ = "packages"

    id          = db.Column(db.Integer, primary_key=True)
    project_id  = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    package_no  = db.Column(db.Integer, default=1)          # 包号 1,2,3...
    name        = db.Column(db.String(200), default="")     # 包内容（可选，后续完善）
    status      = db.Column(db.String(20), default="进行中")  # 进行中|已中标|已签约|已终止
    winner      = db.Column(db.String(200), default="")     # 中标供应商
    win_amount  = db.Column(db.Float, default=0)            # 中标金额
    won_round   = db.Column(db.Integer, default=0)          # 在第几轮中标（0=未中标）
    contract_id = db.Column(db.Integer, default=0)          # 该包唯一的合同 id（0=未签）
    created_at  = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
