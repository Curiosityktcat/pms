from models import db


class ProcurementRound(db.Model):
    """采购轮次（第几次）。

    第一轮在「项目立项 → 采购需求确认」后诞生；之后由「采购结果确认」中出现废标包
    时由系统自动创建下一轮。每一轮拥有自己的采购需求确认 / 采购文件确认状态，
    其采购文件附件、封面、联系人、采购公告、采购结果均归属本轮。
    """
    __tablename__ = "procurement_rounds"

    id            = db.Column(db.Integer, primary_key=True)
    project_id    = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    round_number  = db.Column(db.Integer, default=1)

    # 采购需求确认（5.1）
    demand_confirmed    = db.Column(db.Integer, default=0)
    demand_confirmed_by = db.Column(db.String(100), default="")
    demand_confirmed_at = db.Column(db.String(30), default="")
    # 采购文件确认（5.2）
    doc_confirmed       = db.Column(db.Integer, default=0)
    doc_confirmed_by    = db.Column(db.String(100), default="")
    doc_confirmed_at    = db.Column(db.String(30), default="")
    # 内容确认表所需的代理机构联系人（下沉到轮次）
    doc_agency_contact  = db.Column(db.String(50), default="")
    doc_agency_phone    = db.Column(db.String(50), default="")
    # 驳回（5.1 / 5.2 各自独立，可反复驳回；完整往返链条在 approval_logs）
    demand_reject_reason = db.Column(db.Text, default="")
    demand_reject_count  = db.Column(db.Integer, default=0)
    demand_rejected_by   = db.Column(db.String(50), default="")
    demand_rejected_at   = db.Column(db.String(30), default="")
    doc_reject_reason    = db.Column(db.Text, default="")
    doc_reject_count     = db.Column(db.Integer, default=0)
    doc_rejected_by      = db.Column(db.String(50), default="")
    doc_rejected_at      = db.Column(db.String(30), default="")
    # 项目评审资料审核（8.5）："" 未提交 | 待确认 | 已确认 | 已驳回
    review_status        = db.Column(db.String(10), default="")
    review_confirmed_by  = db.Column(db.String(50), default="")
    review_confirmed_at  = db.Column(db.String(30), default="")
    review_reject_reason = db.Column(db.Text, default="")
    review_reject_count  = db.Column(db.Integer, default=0)
    review_rejected_by   = db.Column(db.String(50), default="")
    review_rejected_at   = db.Column(db.String(30), default="")
    # 开标标记（本轮能否开标）：""未定 | 可开标 | 流标
    can_open    = db.Column(db.String(10), default="")
    can_open_at = db.Column(db.String(30), default="")    # 提交/标记时间（流标=代理提交时间）
    can_open_by = db.Column(db.String(50), default="")    # 提交/标记人
    # 流标两步：代理提交(待确认)→经办人确认(已确认)
    can_open_status       = db.Column(db.String(10), default="")  # ""|待确认|已确认
    can_open_reason       = db.Column(db.String(500), default="") # 流标原因（代理填写）
    can_open_confirmed_by = db.Column(db.String(50), default="")  # 经办人确认人
    can_open_confirmed_at = db.Column(db.String(30), default="")

    status     = db.Column(db.String(20), default="进行中")  # 进行中|已结束
    created_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
