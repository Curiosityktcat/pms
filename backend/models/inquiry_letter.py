from models import db


class InquiryLetter(db.Model):
    __tablename__ = "inquiry_letters"
    id         = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    type       = db.Column(db.String(10), default="询价")   # 询价 | 议价
    title      = db.Column(db.String(200), default="")
    content    = db.Column(db.Text, default="")             # 函件正文（旧版自由文本，保留兼容）
    detail     = db.Column(db.Text, default="")             # 项目细则和限价（默认取项目立项内容，可改）
    requirements = db.Column(db.Text, default="")           # 相关要求（经办人手填）
    deadline   = db.Column(db.String(30), default="")       # 截止回复日期
    status     = db.Column(db.String(10), default="待办")   # 待办|进行中|已完成
    # 轮次覆盖：默认按函件顺序推算；同轮"询价废标转议价"时新函与废标轮同号
    round_no   = db.Column(db.Integer, nullable=True)
    notes      = db.Column(db.Text, default="")
    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
