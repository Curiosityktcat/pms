from . import db


class LlmUsage(db.Model):
    """大模型调用的 token 用量记录（按账号、按功能统计）。"""
    __tablename__ = "llm_usage"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), default="", index=True)  # 调用者账号
    display_name = db.Column(db.String(50), default="")            # 调用者姓名
    feature = db.Column(db.String(40), default="", index=True)     # 功能标识，如 ai-review
    model = db.Column(db.String(80), default="")                   # 所用模型名
    prompt_tokens = db.Column(db.Integer, default=0)
    completion_tokens = db.Column(db.Integer, default=0)
    total_tokens = db.Column(db.Integer, default=0)
    created_at = db.Column(db.String(30), default="", index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username or "",
            "display_name": self.display_name or "",
            "feature": self.feature or "",
            "model": self.model or "",
            "prompt_tokens": self.prompt_tokens or 0,
            "completion_tokens": self.completion_tokens or 0,
            "total_tokens": self.total_tokens or 0,
            "created_at": self.created_at or "",
        }
