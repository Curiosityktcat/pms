from models import db


class ChatMessage(db.Model):
    """一对一聊天消息（文本 / 图片 / 文件）。会话 = 两人之间的消息集合。"""
    __tablename__ = "chat_messages"
    id             = db.Column(db.Integer, primary_key=True)
    sender         = db.Column(db.String(100), index=True)   # 发送者 username
    sender_name    = db.Column(db.String(50), default="")
    recipient      = db.Column(db.String(100), index=True)   # 接收者 username
    recipient_name = db.Column(db.String(50), default="")
    msg_type       = db.Column(db.String(10), default="text")  # text | image | file
    text           = db.Column(db.Text, default="")           # 文本内容 / 文件说明
    file_path      = db.Column(db.String(500), default="")    # 相对 PMS_ROOT
    file_name      = db.Column(db.String(200), default="")    # 原始文件名
    file_size      = db.Column(db.Integer, default=0)
    is_read        = db.Column(db.Integer, default=0)
    read_at        = db.Column(db.String(30), default="")
    created_at     = db.Column(db.String(30), default="", index=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
