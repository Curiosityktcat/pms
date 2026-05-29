from models import db


class ContractAttachment(db.Model):
    __tablename__ = "contract_attachments"

    id            = db.Column(db.Integer, primary_key=True)
    contract_id   = db.Column(db.Integer, db.ForeignKey("contracts.id"), nullable=False)
    original_name = db.Column(db.String(300), default="")
    saved_name    = db.Column(db.String(300), default="")
    file_size     = db.Column(db.Integer, default=0)
    mime_type     = db.Column(db.String(100), default="")
    stage         = db.Column(db.String(10), default="草案")  # 草案 | 上传
    uploaded_by   = db.Column(db.String(50), default="")
    uploaded_at   = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
