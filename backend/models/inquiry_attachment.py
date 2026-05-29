from . import db


class InquiryAttachment(db.Model):
    __tablename__ = "inquiry_attachments"

    id = db.Column(db.Integer, primary_key=True)
    inquiry_id = db.Column(db.Integer, nullable=False, index=True)
    filename = db.Column(db.String(200), default="")
    filepath = db.Column(db.String(500), default="")  # relative to PMS_ROOT
    uploaded_at = db.Column(db.String(30), default="")
    uploaded_by = db.Column(db.String(100), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "inquiry_id": self.inquiry_id,
            "filename": self.filename,
            "filepath": self.filepath,
            "uploaded_at": self.uploaded_at,
            "uploaded_by": self.uploaded_by,
        }
