from datetime import datetime

from . import db


class ApiProvider(db.Model):
    """大模型 API 台账（后台「API 管理」维护）。

    每行一个可用端点：OpenAI 兼容的 chat 或 embeddings 地址。
    「启用」动作把该行写入 sys_config 的全局模型键，业务侧无感切换。
    """
    __tablename__ = "api_providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)        # 显示名，如「agnesai 账号1」
    kind = db.Column(db.String(10), default="chat")          # chat / embed
    base_url = db.Column(db.String(300), default="")         # 完整端点 URL（…/chat/completions 或 …/embeddings）
    model_name = db.Column(db.String(100), default="")
    api_key = db.Column(db.String(300), default="")
    # requests / curl：.12 透明代理下部分外网 API（agnesai、Gemini）用
    # python requests 会挂死，必须走 curl 系统栈
    transport = db.Column(db.String(10), default="requests")
    note = db.Column(db.String(300), default="")
    sort = db.Column(db.Integer, default=0)
    # 最近一次连通测试结果（缓存展示用）
    last_test_ok = db.Column(db.Integer)                     # 1/0，NULL=未测过
    last_test_at = db.Column(db.String(30), default="")
    last_test_msg = db.Column(db.String(300), default="")
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now)

    def masked_key(self):
        k = self.api_key or ""
        if len(k) <= 10:
            return "*" * len(k)
        return f"{k[:6]}…{k[-4:]}"

    def to_dict(self, with_key=False):
        return {
            "id": self.id, "name": self.name, "kind": self.kind,
            "base_url": self.base_url, "model_name": self.model_name,
            "api_key_masked": self.masked_key(),
            **({"api_key": self.api_key} if with_key else {}),
            "transport": self.transport, "note": self.note or "", "sort": self.sort or 0,
            "last_test_ok": self.last_test_ok,
            "last_test_at": self.last_test_at or "",
            "last_test_msg": self.last_test_msg or "",
        }
