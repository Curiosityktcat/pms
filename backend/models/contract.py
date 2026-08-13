from models import db


class Contract(db.Model):
    __tablename__ = "contracts"
    id                 = db.Column(db.Integer, primary_key=True)
    project_id         = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    contract_number    = db.Column(db.String(100), default="")   # 合同编号：项目编号+包号+HT，可修改
    contract_name      = db.Column(db.String(300), default="")   # 合同名称，默认项目名称
    package_no         = db.Column(db.String(10), default="1")   # 包号
    status             = db.Column(db.String(10), default="合同草案")  # 合同草案|合同上传
    # ── 供应商信息（草案阶段填写） ──────────────────────────────────
    supplier_name      = db.Column(db.String(200), default="")   # 成交供应商名称
    supplier_address   = db.Column(db.String(300), default="")   # 地址
    supplier_contact   = db.Column(db.String(100), default="")   # 联系方式
    supplier_legal_rep = db.Column(db.String(50), default="")    # 法人名称
    # ── 合同金额 ──────────────────────────────────────────────────
    amount_is_text     = db.Column(db.Integer, default=0)        # 1=文字金额，0=数字金额
    amount_text        = db.Column(db.String(500), default="")   # 文字金额（如"按招标单价结算"）
    amount             = db.Column(db.Float, default=None)       # 数字金额（元）
    # ── 合同上传阶段 ──────────────────────────────────────────────
    sign_date          = db.Column(db.String(30), default="")    # 签订时间
    service_start      = db.Column(db.String(30), default="")    # 服务期限开始（服务类项目）
    service_end        = db.Column(db.String(30), default="")    # 服务期限结束（服务类项目）
    file_name          = db.Column(db.String(300), default="")   # 上传文件原始名称
    file_saved_name    = db.Column(db.String(300), default="")   # 上传文件保存名称
    notes              = db.Column(db.Text, default="")
    # ── rd-web 合同审签提交 ────────────────────────────────────────
    rdweb_serial_no    = db.Column(db.String(100), default="")   # rd-web 合同审签流水号
    rdweb_submitted_at = db.Column(db.String(30), default="")    # 推送 rd-web 成功时间
    # ── 驳回（打回合同草案重改，完整往返链条在 approval_logs）──────
    reject_reason      = db.Column(db.Text, default="")
    reject_count       = db.Column(db.Integer, default=0)
    rejected_by        = db.Column(db.String(50), default="")
    rejected_at        = db.Column(db.String(30), default="")
    # ── 元数据 ────────────────────────────────────────────────────
    created_by         = db.Column(db.String(50), default="")
    created_at         = db.Column(db.String(30), default="")
    updated_at         = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
