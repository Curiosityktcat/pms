from models import db


class InternalBidDemand(db.Model):
    __tablename__ = "internal_bid_demands"
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)

    # 表头（院内竞选需求是「项目的起点」，项目名称/预算在此手填，不再关联已立项的项目）
    project_name = db.Column(db.String(200), default="")      # 项目名称（手填）
    budget_amount = db.Column(db.Float, nullable=True)        # 1.6 预算金额（手填，元）
    demand_dept = db.Column(db.String(100), default="")       # 需求科室
    manage_dept = db.Column(db.String(100), default="")       # 归口管理科室

    # 第一部分
    year = db.Column(db.String(10), default="")               # 1.2所属年度
    compile_date = db.Column(db.String(30), default="")       # 1.4编制时间
    category = db.Column(db.String(10), default="货物")       # 1.5 货物/服务/工程
    overview = db.Column(db.Text, default="")                 # 1.7项目概况
    has_consultant = db.Column(db.Integer, default=0)         # 1.8 0=否 1=是
    consultant_note = db.Column(db.Text, default="")          # 1.8 若是填写

    # 第三部分
    proc_method = db.Column(db.String(20), default="院内竞选")  # 3.1 院内竞选/院内单一来源
    pkg_split = db.Column(db.String(20), default="不分包采购")  # 3.2 不分包采购/分包采购
    multi_year = db.Column(db.Integer, default=0)              # 3.3 0=否 1=是

    # 第四部分
    items_json = db.Column(db.Text, default="[]")              # 标的情况 JSON
    packages_json = db.Column(db.Text, default="[]")           # 分包情况 JSON

    # 第五/六部分
    tech_req = db.Column(db.Text, default="")                  # 技术要求
    biz_req = db.Column(db.Text, default="")                   # 商务要求

    # 第七部分
    special_qual = db.Column(db.Text, default="")              # 特殊资格要求

    # 第八部分
    review_factors_json = db.Column(db.Text, default="[]")     # 评审因素 JSON

    # 第九部分
    contract_type = db.Column(db.String(200), default="")      # 合同类型（多选逗号分隔）
    actual_settlement = db.Column(db.Integer, default=0)       # 是否据实结算 0=否 1=是
    contract_period = db.Column(db.String(200), default="")    # 合同履行期限
    contract_location = db.Column(db.String(200), default="")  # 合同履约地点
    payment_terms = db.Column(db.Text, default="")             # 合同支付约定
    acceptance_standard = db.Column(db.Text, default="")       # 验收交付标准和方法
    warranty = db.Column(db.Text, default="")                  # 质量保修范围和保修期
    ip_ownership = db.Column(db.Text, default="")              # 知识产权归属
    cost_risk = db.Column(db.Text, default="")                 # 成本补偿和风险分担约定
    breach_dispute = db.Column(db.Text, default="")            # 违约责任与解决争议的方法
    contract_other = db.Column(db.Text, default="")            # 合同其他条款
    perf_bond = db.Column(db.Integer, default=0)               # 履约保证金 0=否 1=是
    perf_bond_ratio = db.Column(db.String(100), default="")    # 比例
    perf_bond_method = db.Column(db.String(100), default="")   # 缴纳方式
    perf_bond_note = db.Column(db.Text, default="")            # 缴纳说明
    quality_bond = db.Column(db.Integer, default=1)            # 质量保证金 默认是

    # 第十部分
    accept_org = db.Column(db.String(30), default="自行验收")   # 验收组织方式
    invite_supplier = db.Column(db.Integer, default=0)
    invite_expert = db.Column(db.Integer, default=0)
    invite_service = db.Column(db.Integer, default=0)
    invite_third = db.Column(db.Integer, default=0)
    accept_procedure = db.Column(db.Text, default="")
    accept_time = db.Column(db.Text, default="")
    accept_other = db.Column(db.Text, default="")
    tech_accept = db.Column(db.Text, default="")
    biz_accept = db.Column(db.Text, default="")
    accept_std = db.Column(db.Text, default="")
    accept_other2 = db.Column(db.Text, default="")

    status = db.Column(db.String(10), default="初稿")          # 初稿/定稿
    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
