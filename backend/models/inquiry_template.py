from . import db


class InquiryTemplate(db.Model):
    __tablename__ = "inquiry_templates"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), default="")
    description = db.Column(db.String(500), default="")  # 模板说明
    filepath = db.Column(db.String(500), default="")      # 相对 PMS_ROOT
    uploaded_at = db.Column(db.String(30), default="")
    uploaded_by = db.Column(db.String(100), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "description": self.description,
            "filepath": self.filepath,
            "uploaded_at": self.uploaded_at,
            "uploaded_by": self.uploaded_by,
        }
