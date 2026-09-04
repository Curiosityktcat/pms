from models import db


class DocUploadEvent(db.Model):
    """采购需求/采购文件的上传留痕——只增不改，删了文件也不删这条。

    起因（2026-09-04）：代理机构 7 月 2 日交了第一版采购文件，7 月 6 日换成
    定稿，采购人 7 月 6 日确认。附件删除是硬删除，连文件带记录一起抹掉，
    于是系统里只剩 7-06 那份，考核算出「用时 6 日」——代理白背了 4 天。
    代理手里有截图，系统却拿不出证据。

    所以上传这件事必须和审批留痕（approval_logs）一样只增不改：
    文件可以删、可以换版本，但「谁在几号交了什么」这条记录永远留着。
    考核算时效读的是这张表，不是当前还活着的附件。
    """
    __tablename__ = "doc_upload_events"

    id            = db.Column(db.Integer, primary_key=True)
    project_id    = db.Column(db.Integer, index=True, nullable=False)
    round_number  = db.Column(db.Integer, default=1)
    kind          = db.Column(db.String(20), default="", index=True)  # demand|doc|result|...
    action        = db.Column(db.String(10), default="upload")        # upload|delete
    # 指向当时那条附件；附件被删了这里就成了悬空 id，是有意为之——
    # 用它把 upload 和后来的 delete 对上，不是外键。
    attachment_id = db.Column(db.Integer, nullable=True, index=True)

    original_name = db.Column(db.String(300), default="")
    file_size     = db.Column(db.Integer, default=0)
    sha256        = db.Column(db.String(64), default="")

    operator      = db.Column(db.String(100), default="")
    operator_name = db.Column(db.String(50), default="")
    operator_role = db.Column(db.String(20), default="")
    created_at    = db.Column(db.String(30), default="", index=True)

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
