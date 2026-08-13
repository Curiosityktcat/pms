from . import db

QUALIFICATIONS_DEFAULT = (
    '（一）在中华人民共和国境内注册，具有独立法人资格；\n'
    '（二）具有良好的商业信誉和健全的财务会计制度；\n'
    '（三）具备履行合同所必需的设备和专业技术能力；\n'
    '（四）参加采购活动前三年内，在经营活动中没有重大违法记录；\n'
    '（五）本项目不接受联合体；\n'
    '（六）本项目规定的其他要求：'
)


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    ann_type = db.Column(db.String(20), default="procurement")
    round_number = db.Column(db.Integer, default=1)

    # 正文内容
    project_intro = db.Column(db.Text, default="")
    qualifications = db.Column(db.Text, default=QUALIFICATIONS_DEFAULT)  # 一般资格要求（整段）
    special_req = db.Column(db.Text, default="")                          # 特殊要求（第七项）

    # 时间
    reg_start = db.Column(db.String(60), default="")
    reg_end = db.Column(db.String(60), default="")
    reg_note = db.Column(db.Text, default="")
    response_deadline = db.Column(db.String(60), default="")

    # 代理机构信息
    agency_address = db.Column(db.String(200), default="")
    delivery_address = db.Column(db.String(200), default="")
    agency_email = db.Column(db.String(100), default="")
    agency_reg_phone = db.Column(db.String(60), default="")
    agency_contact = db.Column(db.String(60), default="")
    agency_contact_phone = db.Column(db.String(60), default="")

    # ── 更正公告（ann_type='correction'）专用字段 ─────────────────
    corr_scope = db.Column(db.String(30), default="")        # 更正事项：采购公告 / 采购文件 / 采购公告、采购文件
    corr_reason = db.Column(db.Text, default="")             # 更正原因（简述）
    corr_items_json = db.Column(db.Text, default="[]")       # [{"item":..,"before":..,"after":..}]
    corr_in_attachment = db.Column(db.Integer, default=0)    # 1=更正内容较多，详见附件
    corr_seq = db.Column(db.Integer, default=1)              # 本项目本轮第几次更正（标题用）

    # ── 调研公告（ann_type='survey'）专用字段 ──────────────────────
    # 体例照内江一院官网已发布的市场调研公告（如云算力、法律顾问两份）
    survey_content       = db.Column(db.Text, default="")    # 一、调研内容及技术/服务要求
    survey_qualification = db.Column(db.Text, default="")    # 二、供应商资格要求
    survey_quote_req     = db.Column(db.Text, default="")    # 三、报价要求
    survey_materials     = db.Column(db.Text, default="")    # 四、需提交的资料清单
    survey_deadline      = db.Column(db.String(60), default="")   # 提交截止时间
    survey_submit_way    = db.Column(db.Text, default="")    # 提交方式（邮箱/纸质地址）
    survey_note          = db.Column(db.Text, default="")    # 特别说明（默认含"与采购结果无必然联系"）

    # ── 单一来源公示（ann_type='single_source'）专用字段 ────────────
    # 必备内容按《政府采购非招标采购方式管理办法》（财政部令第74号）第38条
    ss_goods_desc     = db.Column(db.Text, default="")       # 拟采购的货物或服务说明
    ss_reason         = db.Column(db.Text, default="")       # 采用单一来源方式的原因及说明
    ss_supplier_name  = db.Column(db.String(200), default="")  # 拟定唯一供应商名称
    ss_supplier_addr  = db.Column(db.String(300), default="")  # 唯一供应商地址
    ss_experts_json   = db.Column(db.Text, default="[]")     # [{name,org,title,opinion}] 专家论证意见
    ss_publicity_start = db.Column(db.String(60), default="")  # 公示期起（法定不少于5个工作日）
    ss_publicity_end   = db.Column(db.String(60), default="")  # 公示期止
    ss_objection_dept  = db.Column(db.String(120), default="")  # 异议接收部门
    ss_objection_contact = db.Column(db.String(60), default="")
    ss_objection_phone   = db.Column(db.String(60), default="")
    ss_objection_addr    = db.Column(db.String(300), default="")

    # 状态：草稿 → 待确认 →（经办人）已确认 / 已驳回 →（代理改后重提）待确认
    status = db.Column(db.String(20), default="草稿")
    confirmed_by = db.Column(db.String(50), default="")
    confirmed_at = db.Column(db.String(30), default="")
    # 驳回：原因保留在单据上供代理机构直接看到，完整往返链条在 approval_logs
    reject_reason = db.Column(db.Text, default="")
    reject_count = db.Column(db.Integer, default=0)
    rejected_by = db.Column(db.String(50), default="")
    rejected_at = db.Column(db.String(30), default="")

    created_at = db.Column(db.String(30), default="")
    created_by = db.Column(db.String(50), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "ann_type": self.ann_type,
            "round_number": self.round_number,
            "project_intro": self.project_intro or "",
            "qualifications": self.qualifications or QUALIFICATIONS_DEFAULT,
            "special_req": self.special_req or "",
            "reg_start": self.reg_start or "",
            "reg_end": self.reg_end or "",
            "reg_note": self.reg_note or "",
            "response_deadline": self.response_deadline or "",
            "agency_address": self.agency_address or "",
            "delivery_address": self.delivery_address or "",
            "agency_email": self.agency_email or "",
            "agency_reg_phone": self.agency_reg_phone or "",
            "agency_contact": self.agency_contact or "",
            "agency_contact_phone": self.agency_contact_phone or "",
            "corr_scope": self.corr_scope or "",
            "corr_reason": self.corr_reason or "",
            "corr_items_json": self.corr_items_json or "[]",
            "corr_in_attachment": int(self.corr_in_attachment or 0),
            "corr_seq": int(self.corr_seq or 1),
            "survey_content": self.survey_content or "",
            "survey_qualification": self.survey_qualification or "",
            "survey_quote_req": self.survey_quote_req or "",
            "survey_materials": self.survey_materials or "",
            "survey_deadline": self.survey_deadline or "",
            "survey_submit_way": self.survey_submit_way or "",
            "survey_note": self.survey_note or "",
            "ss_goods_desc": self.ss_goods_desc or "",
            "ss_reason": self.ss_reason or "",
            "ss_supplier_name": self.ss_supplier_name or "",
            "ss_supplier_addr": self.ss_supplier_addr or "",
            "ss_experts_json": self.ss_experts_json or "[]",
            "ss_publicity_start": self.ss_publicity_start or "",
            "ss_publicity_end": self.ss_publicity_end or "",
            "ss_objection_dept": self.ss_objection_dept or "",
            "ss_objection_contact": self.ss_objection_contact or "",
            "ss_objection_phone": self.ss_objection_phone or "",
            "ss_objection_addr": self.ss_objection_addr or "",
            "status": self.status or "草稿",
            "confirmed_by": self.confirmed_by or "",
            "confirmed_at": self.confirmed_at or "",
            "reject_reason": self.reject_reason or "",
            "reject_count": int(self.reject_count or 0),
            "rejected_by": self.rejected_by or "",
            "rejected_at": self.rejected_at or "",
            "created_at": self.created_at or "",
            "created_by": self.created_by or "",
        }
