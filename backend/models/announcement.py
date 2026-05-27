from . import db

QUAL_DEFAULTS = [
    '（一）在中华人民共和国境内注册，具有独立法人资格；',
    '（二）具有良好的商业信誉和健全的财务会计制度；',
    '（三）具备履行合同所必需的设备和专业技术能力；',
    '（四）参加采购活动前三年内，在经营活动中没有重大违法记录；',
    '（五）本项目不接受联合体；',
    '（六）本项目规定的其他要求：',
]


class Announcement(db.Model):
    __tablename__ = "announcements"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, nullable=False)
    ann_type = db.Column(db.String(20), default="procurement")  # procurement | survey | correction | single_source
    round_number = db.Column(db.Integer, default=1)

    # 正文内容
    project_intro = db.Column(db.Text, default="")       # 招标项目简介
    special_req = db.Column(db.Text, default="")         # 特殊要求（第七项）

    # 一般资格要求（6条，可单独编辑）
    qual_1 = db.Column(db.Text, default=QUAL_DEFAULTS[0])
    qual_2 = db.Column(db.Text, default=QUAL_DEFAULTS[1])
    qual_3 = db.Column(db.Text, default=QUAL_DEFAULTS[2])
    qual_4 = db.Column(db.Text, default=QUAL_DEFAULTS[3])
    qual_5 = db.Column(db.Text, default=QUAL_DEFAULTS[4])
    qual_6 = db.Column(db.Text, default=QUAL_DEFAULTS[5])

    # 时间
    reg_start = db.Column(db.String(60), default="")          # 报名开始日期 e.g. "2026年6月1日"
    reg_end = db.Column(db.String(60), default="")            # 报名截止日期 e.g. "2026年6月10日"
    reg_note = db.Column(db.Text, default="")                 # 报名备注，如"注：...报名时间（上午...）"
    response_deadline = db.Column(db.String(60), default="")  # 响应文件截止时间 e.g. "2026年6月20日15:00"

    # 代理机构信息（生成公告时填写）
    agency_address = db.Column(db.String(200), default="")       # 代理机构地址（取文件/递交地点）
    delivery_address = db.Column(db.String(200), default="")     # 递交响应文件地点（可与上同）
    agency_email = db.Column(db.String(100), default="")         # 代理机构邮箱
    agency_reg_phone = db.Column(db.String(60), default="")      # 报名咨询电话
    agency_contact = db.Column(db.String(60), default="")        # 代理联系人
    agency_contact_phone = db.Column(db.String(60), default="")  # 代理联系电话

    # 状态：草稿 → 待确认 → 已确认
    status = db.Column(db.String(20), default="草稿")
    confirmed_by = db.Column(db.String(50), default="")
    confirmed_at = db.Column(db.String(30), default="")

    created_at = db.Column(db.String(30), default="")
    created_by = db.Column(db.String(50), default="")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "ann_type": self.ann_type,
            "round_number": self.round_number,
            "project_intro": self.project_intro or "",
            "special_req": self.special_req or "",
            # 一般资格要求
            "qual_1": self.qual_1 or QUAL_DEFAULTS[0],
            "qual_2": self.qual_2 or QUAL_DEFAULTS[1],
            "qual_3": self.qual_3 or QUAL_DEFAULTS[2],
            "qual_4": self.qual_4 or QUAL_DEFAULTS[3],
            "qual_5": self.qual_5 or QUAL_DEFAULTS[4],
            "qual_6": self.qual_6 or QUAL_DEFAULTS[5],
            # 时间
            "reg_start": self.reg_start or "",
            "reg_end": self.reg_end or "",
            "reg_note": self.reg_note or "",
            "response_deadline": self.response_deadline or "",
            # 代理信息
            "agency_address": self.agency_address or "",
            "delivery_address": self.delivery_address or "",
            "agency_email": self.agency_email or "",
            "agency_reg_phone": self.agency_reg_phone or "",
            "agency_contact": self.agency_contact or "",
            "agency_contact_phone": self.agency_contact_phone or "",
            # 状态
            "status": self.status or "草稿",
            "confirmed_by": self.confirmed_by or "",
            "confirmed_at": self.confirmed_at or "",
            "created_at": self.created_at or "",
            "created_by": self.created_by or "",
        }
