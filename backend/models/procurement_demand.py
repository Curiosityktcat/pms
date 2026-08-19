import json
from models import db


class ProcurementDemand(db.Model):
    __tablename__ = "procurement_demands"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=True)   # 立项后填入

    # ── 需求类型 ─────────────────────────────────────────────────────
    # gov=政府采购  competition=院内竞选  sole_source=单一来源  inquiry=询议价
    demand_type = db.Column(db.String(20), default="competition")

    # ── 流程状态：草稿 → 待分发 → 已分发 → 已立项 ──────────────────
    status = db.Column(db.String(20), default="草稿")
    version = db.Column(db.Integer, default=1)

    # ── 表头 ─────────────────────────────────────────────────────────
    demand_dept  = db.Column(db.String(100), default="")
    manage_dept  = db.Column(db.String(100), default="医学装备部")
    project_name = db.Column(db.String(300), default="")

    # ── 第一部分 ─────────────────────────────────────────────────────
    year          = db.Column(db.String(10),  default="")
    compile_date  = db.Column(db.String(30),  default="")
    category      = db.Column(db.String(10),  default="货物")
    budget_amount = db.Column(db.Float,        default=0)
    project_overview          = db.Column(db.Text, default="")
    has_related_supplier      = db.Column(db.String(10), default="否")

    # ── 第二部分：需求调查（政府采购必填，自行采购可选）──────────────
    survey_needed   = db.Column(db.String(5), default="不需要")   # 需要/不需要
    survey_industry = db.Column(db.Text, default="")   # 2.1 相关产业发展情况
    survey_market   = db.Column(db.Text, default="")   # 2.2 市场供给情况
    survey_history  = db.Column(db.Text, default="")   # 2.3 同类项目历史成交信息
    survey_followup = db.Column(db.Text, default="")   # 2.4 后续采购情况
    survey_other    = db.Column(db.Text, default="")   # 2.5 其他相关情况
    survey_content  = db.Column(db.Text, default="")   # 非政府采购汇总文本（保留兼容）

    # ── 第三部分：采购实施计划 ────────────────────────────────────────
    # 政府采购专用
    org_form      = db.Column(db.String(20), default="")   # 3.1 采购组织形式
    budget_method = db.Column(db.String(30), default="")   # 3.2 采购方式
    # 通用
    procurement_method = db.Column(db.String(20), default="院内竞选")
    package_split      = db.Column(db.String(10), default="不分包采购")  # 3.3
    is_multi_year      = db.Column(db.String(5),  default="否")          # 3.4
    # 政府采购3.5~3.11
    sme_policy        = db.Column(db.Text,       default="")    # 3.5 执行中小企业发展政策
    is_eco_product    = db.Column(db.String(5),  default="否")  # 3.6 环境标识产品
    is_energy_save    = db.Column(db.String(5),  default="否")  # 3.7 节能产品
    has_import_product= db.Column(db.String(5),  default="否")  # 3.8 含进口产品
    is_govt_service   = db.Column(db.String(5),  default="否")  # 3.9 政府购买服务
    is_info_system    = db.Column(db.String(5),  default="否")  # 3.10 政务信息系统
    is_research_equip = db.Column(db.String(5),  default="否")  # 3.11 科研设备
    # 单一来源专用
    sole_source_reason = db.Column(db.Text, default="")

    # ── 第四部分：标的（JSON） ────────────────────────────────────────
    items_json       = db.Column(db.Text,      default="[]")
    # 分包：每个包就是一份独立合同，第四~第八部分各填一份
    # （黄新博 2026-08-19 ⑥⑪：「每个包的情况都要单独填写」）。
    # 单包项目也存成一条，出稿逻辑不用分两套。
    packages_json    = db.Column(db.Text,      default="[]")
    package_count    = db.Column(db.Integer,   default=1)
    max_price        = db.Column(db.Float,     default=0)        # 最高限价（政府采购包级）
    pricing_method   = db.Column(db.String(30), default="")      # 4.2.3 定价方式
    allow_consortium = db.Column(db.String(5),  default="否")    # 4.2.4 支持联合体投标
    allow_subcontract= db.Column(db.String(5),  default="否")    # 4.2.5 允许合同分包

    # ── 第五～七部分 ──────────────────────────────────────────────────
    tech_requirements          = db.Column(db.Text, default="")
    business_requirements      = db.Column(db.Text, default="")
    qualification_requirements = db.Column(db.Text, default="")

    # ── 第八部分：评审因素（仅政府采购）─────────────────────────────
    eval_method          = db.Column(db.String(30), default="")  # 综合评分法/最低评标价法/性价比法
    eval_price_score     = db.Column(db.Float,       default=0)
    eval_tech_criteria   = db.Column(db.Text,        default="")
    eval_service_criteria = db.Column(db.Text,       default="")

    # ── 第九部分：合同管理 ─────────────────────────────────────────
    contract_type      = db.Column(db.String(100), default="")   # 9.1 合同类型
    contract_is_actual = db.Column(db.String(5),   default="否") # 9.2
    contract_period    = db.Column(db.String(200), default="")   # 9.3
    contract_location  = db.Column(db.String(200), default="")   # 9.4 合同履约地点
    payment_terms      = db.Column(db.Text,        default="")   # 9.5
    acceptance_delivery= db.Column(db.Text,        default="")   # 9.6 验收交付标准
    warranty_terms     = db.Column(db.Text,        default="")   # 9.7 质量保修
    ip_terms           = db.Column(db.Text,        default="")   # 9.8 知识产权
    cost_risk_terms    = db.Column(db.Text,        default="")   # 9.9 成本补偿与风险
    breach_terms       = db.Column(db.Text,        default="")   # 9.10
    other_contract_terms=db.Column(db.Text,        default="")   # 9.11 合同其他条款
    performance_bond_terms=db.Column(db.Text,      default="")   # 9.12 履约保证

    # ── 第十部分：履约验收 ─────────────────────────────────────────
    acceptance_org          = db.Column(db.String(50),  default="")  # 10.1 验收组织方式
    invite_other_supplier   = db.Column(db.String(5),   default="否") # 10.2
    invite_expert           = db.Column(db.String(5),   default="否") # 10.3
    invite_service_obj      = db.Column(db.String(5),   default="否") # 10.4
    invite_third_party      = db.Column(db.String(5),   default="否") # 10.5
    acceptance_procedure    = db.Column(db.Text,        default="")   # 10.6
    acceptance_time         = db.Column(db.String(200), default="")   # 10.7
    acceptance_misc         = db.Column(db.Text,        default="")   # 10.8 其他事项
    acceptance_tech         = db.Column(db.Text,        default="")   # 10.9
    acceptance_biz          = db.Column(db.Text,        default="")   # 10.10
    acceptance_standard     = db.Column(db.Text,        default="")   # 10.11
    acceptance_extra        = db.Column(db.Text,        default="")   # 10.12

    # ── 第十一部分：风险控制（仅政府采购）──────────────────────────
    risk_needed   = db.Column(db.String(5), default="否")
    risk_measures = db.Column(db.Text,      default="")

    # ── 审签 ───────────────────────────────────────────────────────
    handler_name      = db.Column(db.String(50), default="")
    manager_opinion   = db.Column(db.Text,       default="")
    legal_opinion     = db.Column(db.Text,       default="")
    audit_opinion     = db.Column(db.Text,       default="")
    leader_opinion    = db.Column(db.Text,       default="")
    cfo_opinion       = db.Column(db.Text,       default="")
    president_opinion = db.Column(db.Text,       default="")

    # ── 分发信息 ────────────────────────────────────────────────────
    assigned_officer     = db.Column(db.String(50), default="")
    assigned_agency_code = db.Column(db.String(20), default="")
    dispatched_by        = db.Column(db.String(50), default="")
    dispatched_at        = db.Column(db.String(30), default="")

    # ── 询议价专用字段 ──────────────────────────────────────────────
    inq_after_sales        = db.Column(db.Text,        default="")   # 售后服务要求
    inq_delivery_time      = db.Column(db.String(200), default="")   # 交付时间
    inq_delivery_location  = db.Column(db.String(200), default="")   # 服务/交付地点
    inq_performance_bond   = db.Column(db.String(100), default="不收取")  # 履约保证金
    inq_other_requirements = db.Column(db.Text,        default="")   # 其他要求

    # ── 紧急采购专用字段 ────────────────────────────────────────────
    apply_time           = db.Column(db.String(30),  default="")   # 申请时间
    expected_use_time    = db.Column(db.String(30),  default="")   # 预计使用紧急耗材时间
    consumable_name      = db.Column(db.String(200), default="")   # 耗材通用名
    consumable_unit_price= db.Column(db.Float,       default=0)    # 预算单价（元）
    consumable_unit      = db.Column(db.String(20),  default="")   # 单位
    apply_quantity       = db.Column(db.Integer,     default=0)    # 申请数量
    manufacturer         = db.Column(db.String(200), default="")   # 生产厂家
    model_spec           = db.Column(db.String(200), default="")   # 型号
    purpose_type         = db.Column(db.String(20),  default="")   # 用途：手术/治疗/检查
    license_number       = db.Column(db.String(100), default="")   # 耗材使用证（注册证号）
    has_similar_product  = db.Column(db.String(5),   default="无") # 院内有无类似产品
    needs_companion      = db.Column(db.String(5),   default="无需")# 是否需要配套设备/器械
    surgery_name         = db.Column(db.String(200), default="")   # 手术名称（用途=手术时填）
    surgery_level        = db.Column(db.String(50),  default="")   # 手术级别
    import_domestic      = db.Column(db.String(10),  default="")   # 进口/国产
    product_on_catalog   = db.Column(db.String(20),  default="")   # 挂网产品/非挂网产品
    applicable_scope     = db.Column(db.String(10),  default="")   # 适用范围（1/2/3/4）
    clinical_use_desc    = db.Column(db.Text,        default="")   # 申购耗材用途
    attachment_path      = db.Column(db.String(500), default="")   # 情况说明及病历资料附件路径

    # ── 元数据 ─────────────────────────────────────────────────────
    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        try:
            d["items"] = json.loads(self.items_json or "[]")
        except Exception:
            d["items"] = []
        return d
