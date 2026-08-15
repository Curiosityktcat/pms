"""登录账号管理操作留痕。"""
from datetime import datetime

from . import db


class UserAuditLog(db.Model):
    __tablename__ = "user_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor = db.Column(db.String(100), nullable=False, default="")
    actor_name = db.Column(db.String(50), default="")
    action = db.Column(db.String(20), nullable=False)
    target_id = db.Column(db.Integer, nullable=True, index=True)
    target_username = db.Column(db.String(100), nullable=False, default="", index=True)
    # 只保存发生变化的普通字段；密码相关内容无论明文、salt 还是 hash 都不得进入审计表。
    detail = db.Column(db.Text, nullable=False, default="{}")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.now)

    def to_dict(self):
        import json
        try:
            detail = json.loads(self.detail or "{}")
        except (TypeError, ValueError):
            detail = {}
        return {
            "id": self.id,
            "actor": self.actor,
            "actor_name": self.actor_name or "",
            "action": self.action,
            "target_id": self.target_id,
            "target_username": self.target_username,
            "detail": detail,
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
        }
