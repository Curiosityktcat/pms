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
            "status": self.status or "草稿",
            "confirmed_by": self.confirmed_by or "",
            "confirmed_at": self.confirmed_at or "",
            "created_at": self.created_at or "",
            "created_by": self.created_by or "",
        }
