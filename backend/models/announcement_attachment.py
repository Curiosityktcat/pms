from . import db


class AnnouncementAttachment(db.Model):
    __tablename__ = "announcement_attachments"

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, nullable=False, index=True)
    original_name = db.Column(db.String(200))   # 用户上传时的原始文件名
    saved_name = db.Column(db.String(200))       # 服务器存储的文件名（UUID防冲突）
    file_size = db.Column(db.Integer, default=0) # 字节数
    uploaded_by = db.Column(db.String(50), default="")
    uploaded_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "announcement_id": self.announcement_id,
            "original_name": self.original_name or "",
            "file_size": self.file_size or 0,
            "uploaded_by": self.uploaded_by or "",
            "uploaded_at": self.uploaded_at or "",
        }
