from models import db


class Message(db.Model):
    """站内信：一条消息一个收件人（群发时按收件人拆成多条，便于各自标记已读）。"""
    __tablename__ = "messages"
    id             = db.Column(db.Integer, primary_key=True)
    sender         = db.Column(db.String(100), index=True)   # 发件人 username
    sender_name    = db.Column(db.String(50), default="")
    recipient      = db.Column(db.String(100), index=True)   # 收件人 username
    recipient_name = db.Column(db.String(50), default="")
    subject        = db.Column(db.String(200), default="")
    body           = db.Column(db.Text, default="")
    related_project_id   = db.Column(db.Integer, nullable=True)
    related_project_name = db.Column(db.String(200), default="")
    parent_id      = db.Column(db.Integer, nullable=True)    # 回复时指向原信
    is_read        = db.Column(db.Integer, default=0)
    read_at        = db.Column(db.String(30), default="")
    sender_deleted    = db.Column(db.Integer, default=0)     # 发件人在发件箱删除
    recipient_deleted = db.Column(db.Integer, default=0)     # 收件人在收件箱删除
    created_at     = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
