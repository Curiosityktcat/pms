from models import db


class Todo(db.Model):
    """待办事项：指派给某人（owner），可由本人或他人创建。"""
    __tablename__ = "todos"
    id          = db.Column(db.Integer, primary_key=True)
    owner       = db.Column(db.String(100), index=True)    # 负责人 username
    owner_name  = db.Column(db.String(50), default="")
    title       = db.Column(db.String(200), default="")
    content     = db.Column(db.Text, default="")
    status      = db.Column(db.String(10), default="待办")  # 待办 | 已完成
    priority    = db.Column(db.String(10), default="普通")  # 普通 | 重要 | 紧急
    due_date    = db.Column(db.String(30), default="")      # 截止日期（选填）
    related_project_id   = db.Column(db.Integer, nullable=True)
    related_project_name = db.Column(db.String(200), default="")
    created_by      = db.Column(db.String(100), default="")
    created_by_name = db.Column(db.String(50), default="")
    created_at  = db.Column(db.String(30), default="")
    done_at     = db.Column(db.String(30), default="")
    done_by     = db.Column(db.String(50), default="")
    # 系统事件自动派单：source=system 的待办随事项完成自动消除，不可手动操作
    source      = db.Column(db.String(10), default="manual")  # manual | system
    source_key  = db.Column(db.String(80), default="", index=True)  # 幂等键 sys:{event}:proj{id}:r{n}

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
