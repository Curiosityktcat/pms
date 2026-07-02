from . import db


class HermesTask(db.Model):
    """指挥 Hermes 去 rd-web 自动填报的任务。

    PMS 把确认好的信息发给本机 Hermes API(127.0.0.1:8645)，Hermes 后台去
    rd-web 填写并提交；PMS 轮询/回调跟踪状态。
    task_type: agency-agreement(代理协议) / procurement-approval(项目审批) / procurement-contract(合同)
    """
    __tablename__ = "hermes_tasks"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(80), unique=True, index=True)  # 唯一任务编号
    task_type = db.Column(db.String(40), default="")             # 业务类型
    action = db.Column(db.String(20), default="create")          # create/review/submit
    project_id = db.Column(db.Integer, index=True)               # 关联 PMS 项目
    title = db.Column(db.String(300), default="")                # 任务标题（项目名等）
    data = db.Column(db.Text, default="")                        # 发给 Hermes 的字段(JSON)
    status = db.Column(db.String(20), default="accepted")        # accepted/processing/completed/failed
    progress = db.Column(db.String(200), default="")             # 进度描述
    message = db.Column(db.String(300), default="")
    result = db.Column(db.Text, default="")                      # 结果(JSON)
    created_by = db.Column(db.String(50), default="")
    created_at = db.Column(db.String(30), default="")
    updated_at = db.Column(db.String(30), default="")

    def to_dict(self):
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}
