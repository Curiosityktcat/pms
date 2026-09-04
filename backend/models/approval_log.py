from models import db


class ApprovalLog(db.Model):
    """审批过程留痕：提交 / 确认 / 驳回 / 不确认 / 复核，逐条记录，永不删除。

    覆盖 5.1 采购需求确认、5.2 采购文件确认、6.1 采购公告、6.3 更正公告、
    8.5 项目评审资料、9 采购结果确认、10 合同签订。

    归档时按 project_id 取全部记录，生成《审批过程记录表》放入归档文件夹，
    所以这张表只增不改——驳回几次就有几条，构成可追溯的修改链条。
    """
    __tablename__ = "approval_logs"

    id            = db.Column(db.Integer, primary_key=True)
    project_id    = db.Column(db.Integer, index=True, nullable=False)
    round_number  = db.Column(db.Integer, default=1)
    node          = db.Column(db.String(20), default="", index=True)  # demand|doc|announcement|...
    node_label    = db.Column(db.String(40), default="")              # 中文节点名，归档直出
    target_id     = db.Column(db.Integer, nullable=True)              # 关联单据 id（公告/结果/合同）
    seq           = db.Column(db.Integer, default=1)                  # 本节点第几次往返

    action        = db.Column(db.String(20), default="")   # submit|confirm|reject|resubmit|not_confirm|recheck|revoke
    action_label  = db.Column(db.String(20), default="")   # 中文动作名
    reason        = db.Column(db.Text, default="")         # 驳回 / 不确认 原由
    # 驳回时逐条列出的问题：[{"category": "agency_doc|demand_change", "text": "..."}]
    # 分类决定考核里扣不扣分——代理机构文件问题才扣，采购需求调整是采购人自己改的，不扣。
    issues_json   = db.Column(db.Text, default="[]")

    # 仅「不确认采购结果」的复核环节使用
    handling      = db.Column(db.String(20), default="")   # 维持原结果|废标|部分废标|顺延候选人
    handling_note = db.Column(db.Text, default="")

    operator      = db.Column(db.String(100), default="")  # username
    operator_name = db.Column(db.String(50), default="")   # 显示名
    operator_role = db.Column(db.String(20), default="")
    created_at    = db.Column(db.String(30), default="")

    def to_dict(self):
        import json
        d = {c.name: getattr(self, c.name) for c in self.__table__.columns}
        try:
            d["issues"] = json.loads(self.issues_json or "[]")
        except Exception:
            d["issues"] = []
        return d
