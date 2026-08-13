"""审批过程留痕的统一入口。

各审批节点（5.1 需求 / 5.2 文件 / 6.1 公告 / 6.3 更正 / 8.5 评审资料 /
9 结果 / 10 合同）在确认、驳回、不确认、复核时都调 log()，写进 approval_logs。
归档时 render_rows() 出表格数据，由 archive 侧生成《审批过程记录表》。

设计要点：只增不改。驳回三次就留三条，加上中间的重新提交，形成
「谁、什么时候、为什么打回、改了几轮」的完整链条，这是归档要的东西。
"""
import datetime

from flask import session

from models import db
from models.approval_log import ApprovalLog

# 节点 → 中文名（与菜单编号对齐，归档表直接用）
NODE_LABELS = {
    "demand":       "采购需求确认（5.1）",
    "doc":          "采购文件确认（5.2）",
    "announcement": "采购公告（6.1）",
    "correction":   "更正公告（6.3）",
    "review":       "项目评审资料（8.5）",
    "result":       "采购结果确认（9）",
    "contract":     "合同签订（10）",
}

ACTION_LABELS = {
    "submit":      "提交",
    "resubmit":    "修改后重新提交",
    "confirm":     "确认通过",
    "reject":      "驳回",
    "not_confirm": "不确认采购结果",
    "recheck":     "复核后重新推送",
    "revoke":      "撤回",
}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def next_seq(project_id, node, round_number=1):
    """本项目本轮该节点已发生过几次往返，从 1 起。"""
    n = db.session.execute(
        db.select(db.func.count(ApprovalLog.id)).where(
            ApprovalLog.project_id == project_id,
            ApprovalLog.node == node,
            ApprovalLog.round_number == (round_number or 1),
        )
    ).scalar() or 0
    return int(n) + 1


def log(project_id, node, action, *, round_number=1, target_id=None,
        reason="", handling="", handling_note=""):
    """写一条审批记录。操作人取当前会话，调用方不用传。

    不 commit——由调用方在自己的事务里一起提交，避免半截状态。
    """
    if not project_id:
        return None
    row = ApprovalLog(
        project_id=project_id,
        round_number=round_number or 1,
        node=node,
        node_label=NODE_LABELS.get(node, node),
        target_id=target_id,
        seq=next_seq(project_id, node, round_number),
        action=action,
        action_label=ACTION_LABELS.get(action, action),
        reason=(reason or "").strip(),
        handling=handling or "",
        handling_note=(handling_note or "").strip(),
        operator=session.get("user", ""),
        operator_name=session.get("display_name", "") or session.get("user", ""),
        operator_role=session.get("role", ""),
        created_at=_now(),
    )
    db.session.add(row)
    return row


def list_for_project(project_id, node=None):
    conds = [ApprovalLog.project_id == project_id]
    if node:
        conds.append(ApprovalLog.node == node)
    rows = db.session.execute(
        db.select(ApprovalLog).where(*conds).order_by(ApprovalLog.id)
    ).scalars().all()
    return [r.to_dict() for r in rows]


def reject_count(project_id, node, round_number=None):
    """该节点被驳回过几次——前端拿来提示「本节点已驳回 N 次」。"""
    conds = [
        ApprovalLog.project_id == project_id,
        ApprovalLog.node == node,
        ApprovalLog.action.in_(("reject", "not_confirm")),
    ]
    if round_number:
        conds.append(ApprovalLog.round_number == round_number)
    return int(db.session.execute(
        db.select(db.func.count(ApprovalLog.id)).where(*conds)
    ).scalar() or 0)


def render_rows(project_id):
    """归档用：按时间顺序拍平成表格行。"""
    out = []
    for r in list_for_project(project_id):
        detail = r["reason"] or ""
        if r["handling"]:
            detail = f"处置：{r['handling']}" + (f"；{r['handling_note']}" if r["handling_note"] else "")
        out.append({
            "序号": len(out) + 1,
            "时间": (r["created_at"] or "").replace("T", " "),
            "环节": r["node_label"],
            "轮次": f"第{r['round_number']}次采购",
            "动作": r["action_label"],
            "操作人": r["operator_name"],
            "原因/说明": detail,
        })
    return out
