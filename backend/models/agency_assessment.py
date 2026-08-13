from models import db


class AgencyAssessment(db.Model):
    """代理机构服务质量考核（一个项目一份）。

    对应客户《招标代理机构服务质量考核评价表》：
      二、考核内容及评分标准 —— 15 个加/扣分项，满分 100，得分 = 100 + 各项加扣分之和
      三、一票否决项目 —— 9 条，命中即一票否决
      四、综合评价 —— 3 项主观勾选 + 文字意见（非评分项）

    其中 6 项能从 PMS 已有数据自动算出建议分（时效类靠时间戳、规范类靠驳回留痕），
    系统给建议值，采购部对接人可改——机器算得出的不让人再算一遍，算不出的才靠人。
    """
    __tablename__ = "agency_assessments"

    id           = db.Column(db.Integer, primary_key=True)
    project_id   = db.Column(db.Integer, index=True, nullable=False)
    project_number = db.Column(db.String(50), default="")
    project_name = db.Column(db.String(200), default="")
    agency_code  = db.Column(db.String(10), default="", index=True)
    agency_name  = db.Column(db.String(100), default="")

    # 15 个评分项：[{key, score, note, auto_score, auto_basis}]
    items_json   = db.Column(db.Text, default="[]")
    # 一票否决：命中的条目 key 列表
    veto_json    = db.Column(db.Text, default="[]")
    veto_note    = db.Column(db.Text, default="")

    # 综合评价（非评分项）：满意 | 一般 | 不满意
    subj_timeliness = db.Column(db.String(10), default="")   # 经办人响应的及时性
    subj_ability    = db.Column(db.String(10), default="")   # 经办人水平和能力
    subj_attitude   = db.Column(db.String(10), default="")   # 合作态度及协调能力
    comment      = db.Column(db.Text, default="")            # 建议或意见

    total_score  = db.Column(db.Float, default=100.0)        # 100 + 各项加扣分之和
    veto_hit     = db.Column(db.Integer, default=0)          # 1=触发一票否决

    status       = db.Column(db.String(10), default="草稿")   # 草稿 | 已提交
    assessor     = db.Column(db.String(50), default="")      # 采购部对接人
    assessed_at  = db.Column(db.String(30), default="")
    created_by   = db.Column(db.String(50), default="")
    created_at   = db.Column(db.String(30), default="")
    updated_at   = db.Column(db.String(30), default="")

    def to_dict(self):
        import json
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        try:
            d["items"] = json.loads(self.items_json or "[]")
        except Exception:
            d["items"] = []
        try:
            d["veto"] = json.loads(self.veto_json or "[]")
        except Exception:
            d["veto"] = []
        return d
