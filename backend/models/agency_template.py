from . import db


class AgencyTemplate(db.Model):
    """代理机构预设模板：存储每家代理机构的常用联系信息，可一键套用到采购公告"""
    __tablename__ = "agency_templates"

    id = db.Column(db.Integer, primary_key=True)
    agency_code = db.Column(db.String(10), nullable=False, index=True)
    template_name = db.Column(db.String(100), nullable=False)   # 模板名称，如"总部地址"

    agency_address = db.Column(db.String(200), default="")
    delivery_address = db.Column(db.String(200), default="")
    agency_email = db.Column(db.String(100), default="")
    agency_reg_phone = db.Column(db.String(60), default="")
    agency_contact = db.Column(db.String(60), default="")
    agency_contact_phone = db.Column(db.String(60), default="")

    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "agency_code": self.agency_code,
            "template_name": self.template_name,
            "agency_address": self.agency_address or "",
            "delivery_address": self.delivery_address or "",
            "agency_email": self.agency_email or "",
            "agency_reg_phone": self.agency_reg_phone or "",
            "agency_contact": self.agency_contact or "",
            "agency_contact_phone": self.agency_contact_phone or "",
            "created_at": self.created_at or "",
            "updated_at": self.updated_at or "",
        }
