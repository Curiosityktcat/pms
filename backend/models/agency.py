from . import db


class Agency(db.Model):
    __tablename__ = "agencies"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    active = db.Column(db.Integer, default=1)
    # 轮派相关：in_rotation=是否参与 7 家顺序轮派（内江市政府采购中心=0，不占轮次）；
    # rotation_seq=轮派顺序（由采购部助理维护，小在前）。
    in_rotation = db.Column(db.Integer, default=1)
    rotation_seq = db.Column(db.Integer, default=0)
    # 机构基本信息（采购部助理手工维护，用于代理协议/合同等自动填充）
    legal_rep = db.Column(db.String(50), default="")   # 法定代表人
    phone = db.Column(db.String(60), default="")        # 联系方式
    address = db.Column(db.String(200), default="")     # 地址
    is_central = db.Column(db.Integer, default=0)        # 1=集中采购机构（内江市政府采购中心）

    def to_dict(self):
        return {
            "id": self.id, "code": self.code, "name": self.name, "active": self.active,
            "in_rotation": self.in_rotation, "rotation_seq": self.rotation_seq,
            "legal_rep": self.legal_rep or "", "phone": self.phone or "",
            "address": self.address or "", "is_central": self.is_central or 0,
        }
