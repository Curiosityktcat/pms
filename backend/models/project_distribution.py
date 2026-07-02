from . import db


class ProjectDistribution(db.Model):
    """采购部助理分发的项目 = 项目立项的起点。

    信息来源：rd-web（医互通）抓取 或 手动录入。仅「指定经办人 + 采购部助理」可见。
    经办人立项时自动带入 名称/内容/预算（可编辑）；附件流转到采购需求编制可直接用。
    """
    __tablename__ = "project_distributions"

    id = db.Column(db.Integer, primary_key=True)
    serial_no = db.Column(db.String(100), default="")     # rd-web 采购需求流水号
    originator = db.Column(db.String(50), default="")     # 发起人（rd-web 流程发起人）
    form_type = db.Column(db.String(40), default="采购需求审签表")  # 来源表单类型（多流程区分）
    name = db.Column(db.String(300), default="")          # 项目名称
    content = db.Column(db.Text, default="")              # 项目内容
    budget = db.Column(db.Float)                          # 预算金额（元）
    price_limit = db.Column(db.Float)                     # 限价金额（元）
    method = db.Column(db.String(50), default="")         # 采购方式（院内竞选/政府采购/...）
    org_form = db.Column(db.String(50), default="")       # 采购组织形式（自行采购/委托代理...）
    manage_dept = db.Column(db.String(100), default="")   # 归口管理科室
    demand_dept = db.Column(db.String(100), default="")   # 需求科室
    project_number = db.Column(db.String(100), default="")# 项目编号（rd-web）
    extra = db.Column(db.Text, default="")                # 各流程专有字段(JSON)：照搬 rd-web 该表单全部字段
    is_central = db.Column(db.Integer, default=0)         # 是否政采中心项目（集采/医疗设备）
    officer = db.Column(db.String(50), default="")        # 指定经办人（display_name）
    agency_code = db.Column(db.String(10), default="")    # 指定代理机构（按规则自动派）
    source = db.Column(db.String(20), default="手动")      # 来源：rd-web / 手动
    status = db.Column(db.String(20), default="待分发")    # 待分发 / 已分发 / 已立项
    project_id = db.Column(db.Integer)                    # 立项后回填关联项目 id
    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class RdwebAccount(db.Model):
    """rd-web（医互通）登录账号维护。账号会变，给陈梦霞(分发抓取)和经办人(执行)自己维护。
    usage='分发' 的账号被抓取程序使用（保存时同步到 SysConfig rdweb_loginuser/password）。"""
    __tablename__ = "rdweb_accounts"

    id = db.Column(db.Integer, primary_key=True)
    owner = db.Column(db.String(50), default="")          # 姓名/用途
    phone = db.Column(db.String(30), default="")          # 登录手机号
    password = db.Column(db.String(100), default="")      # 登录密码
    usage = db.Column(db.String(20), default="执行")       # 分发 / 执行
    note = db.Column(db.String(200), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}


class ProjectDistributionAttachment(db.Model):
    __tablename__ = "project_distribution_attachments"

    id = db.Column(db.Integer, primary_key=True)
    distribution_id = db.Column(db.Integer, nullable=False, index=True)
    category = db.Column(db.String(20), default="附件")    # 附件 / 审签表（流程打印PDF）
    original_name = db.Column(db.String(200))
    saved_name = db.Column(db.String(200))                # UUID 防冲突
    file_size = db.Column(db.Integer, default=0)
    mime_type = db.Column(db.String(100), default="")
    uploaded_by = db.Column(db.String(50), default="")
    uploaded_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
