from models import db


class DeptAnnouncement(db.Model):
    """采购部公告和相关文件（分流页展示）。

    经办人上传 → 陈梦霞（分发岗）审核 → 发布后全员可见可下载。
    """
    __tablename__ = "dept_announcements"
    id          = db.Column(db.Integer, primary_key=True)
    title       = db.Column(db.String(200), default="")
    note        = db.Column(db.Text, default="")            # 说明（选填）
    filename    = db.Column(db.String(300), default="")     # 原始文件名（可空=纯公告）
    saved_name  = db.Column(db.String(100), default="")
    file_size   = db.Column(db.Integer, default=0)
    uploaded_by = db.Column(db.String(50), default="")
    uploaded_at = db.Column(db.String(30), default="")
    status      = db.Column(db.String(10), default="待审核")  # 待审核|已发布|已驳回
    reviewed_by   = db.Column(db.String(50), default="")
    reviewed_at   = db.Column(db.String(30), default="")
    reject_reason = db.Column(db.String(300), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
