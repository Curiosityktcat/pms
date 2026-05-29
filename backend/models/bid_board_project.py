from models import db


class BidBoardProject(db.Model):
    """开标看板项目（抓取医院官网采购公告所得）。

    迁移自旧「采购开标看板」(test/venv) 的 procurement.db -> projects 表。
    抓取字段由 scraper 写入；supervisor（监督人员）为人工指定，抓取时不覆盖。
    """
    __tablename__ = "bid_board_projects"

    number       = db.Column(db.String(120), primary_key=True)  # 采购项目编号（无编号时用 URL: 兜底）
    name         = db.Column(db.Text, default="")
    agency       = db.Column(db.Text, default="")
    deadline     = db.Column(db.String(60), default="")         # 原文开标/递交截止时间
    deadline_iso = db.Column(db.String(30), default="")         # 解析后的 ISO 时间
    url          = db.Column(db.Text, default="")
    supervisor   = db.Column(db.String(50), default="")         # 人工指定的监督人员
    first_seen   = db.Column(db.String(30), default="")
    updated_at   = db.Column(db.String(30), default="")

    def to_dict(self):
        return {
            "number": self.number,
            "name": self.name or "",
            "agency": self.agency or "",
            "deadline": self.deadline or "",
            "deadline_iso": self.deadline_iso or "",
            "url": self.url or "",
            "supervisor": self.supervisor or "",
            "first_seen": self.first_seen or "",
            "updated_at": self.updated_at or "",
        }
