"""当前处理人：每个项目此刻卡在谁手上、卡的是哪个审核环节、已经等了多久。

真源复用系统待办的派单引擎（services.system_todos._EVENTS/_collect）——
待办落给谁，页面上显示的「当前处理人」就是谁，两处永不打架。

给谁用：
  ① 项目流程页 / 项目进展弹窗（build_progress → project.pending）；
  ② 各审核环节列表（5.1 需求、5.2 文件、6.1 公告、6.3 更正、开标、
     8.5 评审资料、9 结果、10 合同、8.1 询议价评审）每行一个「当前处理人」标签。

设计要点：
  * 只读不写，纯派生，任何时刻调用都是当下真值（不像待办表要等对账）；
  * 待办表会因「经办人/代理没有系统账号」而跳过派单，这里不跳——
    照样用项目上的经办人姓名/代理机构名显示，看得见才叫看得到走到哪一步；
  * waiting_since 取该项目本轮最后一次审批动作的时间（approval_logs），
    没有留痕的就退回项目更新时间，用来算「已等 N 天」。
"""
import datetime

from models import db
from models.approval_log import ApprovalLog
from models.agency import Agency
from models.project import Project
from models.user import User
from services import system_todos as sysdo
from services.project_progress import stage_map

# 归属方 → 显示用中文
ROLE_CN = {"officer": "经办人", "agency": "代理机构"}

# 主线环节（决定项目此刻整体走到哪一步）优先，其余为并行事项。
# 顺序即优先级：主线卡住时先显示主线，主线通了才显示并行的授权函/合同/考核等。
_PARALLEL_EVENTS = (
    "corr_confirm", "corr_fix", "auth_letter",
    "contract_draft", "contract_review", "contract_fix", "contract",
    "agency_assess",
)

ARCHIVED_STATUS = "已归档"


def _today():
    return datetime.date.today()


def _days_since(ts):
    """ISO 时间串 → 距今天数（拿不到就 None）。"""
    if not ts:
        return None
    try:
        d = datetime.date.fromisoformat(str(ts)[:10])
    except ValueError:
        return None
    return max((_today() - d).days, 0)


def _last_action_at(pids):
    """{(project_id, round_number): 最后一次审批留痕时间}。"""
    if not pids:
        return {}
    rows = db.session.execute(
        db.select(ApprovalLog.project_id, ApprovalLog.round_number,
                  db.func.max(ApprovalLog.created_at))
        .where(ApprovalLog.project_id.in_(list(pids)))
        .group_by(ApprovalLog.project_id, ApprovalLog.round_number)
    ).all()
    return {(r[0], r[1] or 1): r[2] or "" for r in rows}


def _entry(event, owner, owner_name, since):
    role, title = sysdo._EVENTS[event]
    return {
        "event": event,
        "label": title,                       # 「待确认采购需求（5.1）」
        "role": role,
        "role_label": ROLE_CN.get(role, role),
        "owner": owner or "",                 # username，可能为空（无账号）
        "owner_name": owner_name or "",       # 姓名 / 代理机构名
        "is_reject": event.endswith("_fix") or event == "result_recheck",
        "since": since or "",
        "waiting_days": _days_since(since),
    }


def pending_map(project_ids):
    """批量返回 {project_id: {...当前处理人..., "others": [...]}}。

    没有待处理事项（本轮办完、已归档、草稿）的项目返回 None，调用方按「—」显示。
    """
    ids = [int(i) for i in project_ids or []]
    if not ids:
        return {}

    projects = db.session.execute(
        db.select(Project).where(Project.id.in_(ids))
    ).scalars().all()
    info = stage_map([p.id for p in projects])
    ctx = sysdo.load_ctx([p.id for p in projects])
    last_at = _last_action_at([p.id for p in projects])

    users = db.session.execute(db.select(User).where(User.active == 1)).scalars().all()
    by_username = {u.username: u for u in users}
    by_display = {u.display_name: u for u in users if u.display_name}
    agency_user = {u.agency_code: u for u in users if u.role == "agency" and u.agency_code}
    agency_name = {a.code: (a.name or a.code) for a in db.session.execute(
        db.select(Agency)).scalars().all()}

    out = {pid: None for pid in ids}
    for p in projects:
        if (p.status or "") == ARCHIVED_STATUS or p.is_draft or p.is_deleted:
            continue
        meta = info.get(p.id) or {}
        rnd_no = meta.get("current_round", 1) or 1
        try:
            events = sysdo._collect(p, meta, ctx)
        except Exception:
            events = []
        if not events:
            continue
        since = last_at.get((p.id, rnd_no), "") or (p.updated_at or "")

        entries = []
        for ev in events:
            role = sysdo._EVENTS[ev][0]
            if role == "officer":
                who = sysdo._resolve_officer(p.officer, by_username, by_display)
                owner, owner_name = who if who else ("", p.officer or "")
            else:
                u = agency_user.get(p.agency_code or "")
                owner = u.username if u else ""
                owner_name = ((u.display_name or u.username) if u
                              else agency_name.get(p.agency_code or "", ""))
            entries.append(_entry(ev, owner, owner_name, since))

        # 主线在前，并行事项在后
        entries.sort(key=lambda e: e["event"] in _PARALLEL_EVENTS)
        primary = dict(entries[0])
        primary["others"] = entries[1:]
        primary["current_round"] = rnd_no
        out[p.id] = primary
    return out


def pending_for(project_id):
    """单项目版，取不到返回 None。"""
    return pending_map([project_id]).get(int(project_id))


def attach_pending(rows, id_key="id"):
    """给一批 dict 行就地补 row["pending"]（列表接口统一走这里）。"""
    if not rows:
        return rows
    ids = [r.get(id_key) for r in rows if r.get(id_key)]
    pm = pending_map(ids)
    for r in rows:
        r["pending"] = pm.get(r.get(id_key))
    return rows
