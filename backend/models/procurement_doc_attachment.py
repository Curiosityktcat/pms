from . import db


class ProcurementDocAttachment(db.Model):
    """采购文件编制阶段的上传附件。

    kind: 'demand' 采购需求确认上传 / 'doc' 采购文件确认上传（预留）。
    """
    __tablename__ = "procurement_doc_attachments"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False, index=True)
    kind = db.Column(db.String(10), default="demand", index=True)
    original_name = db.Column(db.String(200))   # 用户上传时的原始文件名
    saved_name = db.Column(db.String(200))       # 服务器存储文件名（UUID 防冲突）
    file_size = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(50), default="")
    uploaded_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "kind": self.kind or "",
            "original_name": self.original_name or "",
            "file_size": self.file_size or 0,
            "uploaded_by": self.uploaded_by or "",
            "uploaded_at": self.uploaded_at or "",
        }
