from datetime import datetime

from . import db


class RdwebPushLog(db.Model):
    """工具页「合同审签推送」的推送记录（持久化，服务重启不丢）。"""
    __tablename__ = "rdweb_push_logs"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), default="")
    display_name = db.Column(db.String(50), default="")
    contract_name = db.Column(db.String(300), default="")
    file_name = db.Column(db.String(200), default="")
    data_json = db.Column(db.Text, default="")            # 提交的完整字段（JSON）
    status = db.Column(db.String(15), default="running")  # running / ok / fail / interrupted
    serial_no = db.Column(db.String(100), default="")
    msg = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.now)
    finished_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username, "display_name": self.display_name,
            "contract_name": self.contract_name, "file_name": self.file_name,
            "status": self.status, "serial_no": self.serial_no or "",
            "msg": self.msg or "",
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else "",
            "finished_at": self.finished_at.strftime("%Y-%m-%d %H:%M:%S") if self.finished_at else "",
        }
