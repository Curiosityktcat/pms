from models import db


class InquiryReview(db.Model):
    """询议价评审记录（评定标报告）—— 每个询/议价函（即每轮邀请）一条。

    项目信息字段是评审时的快照（默认取项目立项内容，可在评审页改），
    打印的评定标报告按本表 + 供应商评审字段生成 Excel。
    """
    __tablename__ = "inquiry_reviews"
    id          = db.Column(db.Integer, primary_key=True)
    inquiry_id  = db.Column(db.Integer, db.ForeignKey("inquiry_letters.id"),
                            nullable=False, unique=True, index=True)
    project_id  = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    round_no    = db.Column(db.Integer, default=1)          # 第N次（按同项目函件顺序）

    # ── 一、项目信息（快照，可改） ──
    project_name   = db.Column(db.String(200), default="")
    project_number = db.Column(db.String(50), default="")
    package_no     = db.Column(db.String(30), default="/")  # 包号
    content        = db.Column(db.Text, default="")          # 采购内容
    budget         = db.Column(db.String(50), default="")    # 预算金额（文本，含"元"）
    review_date    = db.Column(db.String(30), default="")    # 采购时间（选填）
    location       = db.Column(db.String(100), default="审计科")  # 采购地点
    method         = db.Column(db.String(20), default="院内询价")  # 评审办法：院内询价|院内议价

    # ── 三、采购结果 ──
    result_type = db.Column(db.String(10), default="")       # ''|中选|废标
    result_text = db.Column(db.Text, default="")             # 采购结果一句（自动生成可改）
    remark      = db.Column(db.Text, default="")             # 备注

    # ── 四/五、评审地点与委员会、开标情况 ──
    review_place  = db.Column(db.String(200), default="")
    committee     = db.Column(db.Text, default="")
    bid_open_info = db.Column(db.Text, default="")

    status       = db.Column(db.String(10), default="草稿")  # 草稿|已完成
    completed_by = db.Column(db.String(50), default="")
    completed_at = db.Column(db.String(30), default="")

    # ── 提前开启评审（截止日期未到，供应商文件已齐，经办人确认提前开启）──
    early_open    = db.Column(db.Integer, default=0)          # 1=截止前提前开启
    early_open_by = db.Column(db.String(50), default="")     # 确认提前开启的经办人
    early_open_at = db.Column(db.String(30), default="")     # 确认时间
    created_by   = db.Column(db.String(50), default="")
    created_at   = db.Column(db.String(30), default="")
    updated_at   = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class InquirySupplierFile(db.Model):
    """供应商响应文件（邮件附件/邮寄资料扫描件，评审页手动上传）"""
    __tablename__ = "inquiry_supplier_files"
    id          = db.Column(db.Integer, primary_key=True)
    inquiry_id  = db.Column(db.Integer, nullable=False, index=True)
    supplier_id = db.Column(db.Integer, nullable=False, index=True)
    filename    = db.Column(db.String(200), default="")
    filepath    = db.Column(db.String(500), default="")     # 相对 PMS_ROOT
    uploaded_at = db.Column(db.String(30), default="")
    uploaded_by = db.Column(db.String(50), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
