from models import db


class SysConfig(db.Model):
    __tablename__ = "sys_config"
    key        = db.Column(db.String(100), primary_key=True)
    value      = db.Column(db.Text, default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {"key": self.key, "value": self.value, "updated_at": self.updated_at}
