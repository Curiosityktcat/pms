"""系统事件自动派单：按项目当前阶段，给经办人 / 代理机构生成待办，
事项完成（阶段推进）后自动消除。

谁该处理 → 谁收到待办：
  经办人：确认采购需求(5.1) / 确认采购文件(5.2) / 确认采购结果(9) / 签订合同(10)
  代理机构：上传采购文件(5.2) / 发布采购公告(6.1) / 开标(开标管理)

实现：reconcile_system_todos() 用 project_progress.stage_map 算出"此刻应存在的系统待办"
（desired），与库中 source='system' 的待办对账——缺则建、阶段已过则自动完成、
条件回归则重开。幂等键 source_key = sys:{event}:proj{id}:r{round}。
"""
import datetime
import time

from models import db
from models.todo import Todo
from models.project import Project
from models.user import User
from models.procurement_doc_attachment import ProcurementDocAttachment
from services.project_progress import stage_map, AGENCY_TRACK_METHODS

# event → (角色, 标题)。角色决定 owner 取经办人还是代理机构。
_EVENTS = {
    "demand_confirm": ("officer", "待确认采购需求（5.1）"),
    "doc_upload":     ("agency",  "待上传采购文件（5.2）"),
    "doc_confirm":    ("officer", "待确认采购文件（5.2）"),
    "announce":       ("agency",  "待发布采购公告（6.1）"),
    "bid_open":       ("agency",  "待开标（开标管理）"),
    "result":         ("officer", "待确认采购结果（9）"),
    "contract":       ("officer", "待签订合同（10）"),
}

_THROTTLE_SEC = 25
_last_run = 0.0


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def maybe_reconcile():
    """带节流的对账入口（供高频接口如 summary/list_todos 调用）。"""
    global _last_run
    now = time.time()
    if now - _last_run < _THROTTLE_SEC:
        return
    _last_run = now
    try:
        reconcile_system_todos()
    except Exception:
        db.session.rollback()


def _resolve_officer(officer_name, users_by_username, users_by_display):
    """经办人姓名 → (username, display_name)，无账号则 None。"""
    if not officer_name:
        return None
    u = users_by_username.get(officer_name) or users_by_display.get(officer_name)
    if not u:
        return None
    return u.username, (u.display_name or u.username)


def reconcile_system_todos():
    projects = db.session.execute(
        db.select(Project).where(
            db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
            db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
        )
    ).scalars().all()
    if not projects:
        _complete_orphans({}, None)
        db.session.commit()
        return

    info = stage_map([p.id for p in projects])

    users = db.session.execute(db.select(User).where(User.active == 1)).scalars().all()
    users_by_username = {u.username: u for u in users}
    users_by_display = {u.display_name: u for u in users if u.display_name}
    agency_by_code = {u.agency_code: u for u in users
                      if u.role == "agency" and u.agency_code}

    # 本轮有无"采购文件(doc)"上传，决定 5.2 是代理待上传还是经办人待确认
    doc_uploaded = set()
    for a in db.session.execute(
        db.select(ProcurementDocAttachment).where(
            ProcurementDocAttachment.kind == "doc")
    ).scalars().all():
        doc_uploaded.add((a.project_id, a.round_number or 1))

    desired = {}
    for p in projects:
        meta = info.get(p.id) or {}
        stage = meta.get("current_stage", "")
        rnd = meta.get("current_round", 1) or 1
        pending_contract = meta.get("pending_contract", 0)

        agency_track = (p.method or "") in AGENCY_TRACK_METHODS
        events = []
        if stage == "demand_confirm":
            events.append("demand_confirm")
        elif stage == "doc_confirm":
            # 仅代理制项目走"代理上传→经办人确认"两步；非代理由经办人直接确认
            if agency_track and (p.id, rnd) not in doc_uploaded:
                events.append("doc_upload")
            else:
                events.append("doc_confirm")
        elif stage == "announce":
            events.append("announce")
        elif stage == "bid_open":
            events.append("bid_open")
        elif stage == "result":
            events.append("result")
        if pending_contract > 0:
            events.append("contract")

        for event in events:
            role, title = _EVENTS[event]
            if role == "officer":
                who = _resolve_officer(p.officer, users_by_username, users_by_display)
            else:
                u = agency_by_code.get(p.agency_code or "")
                who = (u.username, u.display_name or u.username) if u else None
            if not who:
                continue
            owner, owner_name = who
            key = f"sys:{event}:proj{p.id}:r{rnd}"
            desired[key] = {
                "owner": owner, "owner_name": owner_name,
                "title": title,
                "related_project_id": p.id,
                "related_project_name": p.name,
            }

    existing = db.session.execute(
        db.select(Todo).where(Todo.source == "system")
    ).scalars().all()
    existing_by_key = {t.source_key: t for t in existing}

    now = _now()
    for key, d in desired.items():
        t = existing_by_key.get(key)
        if t is None:
            db.session.add(Todo(
                owner=d["owner"], owner_name=d["owner_name"],
                title=d["title"], content="",
                status="待办", priority="重要",
                related_project_id=d["related_project_id"],
                related_project_name=d["related_project_name"],
                created_by="system", created_by_name="系统",
                created_at=now, source="system", source_key=key,
            ))
        else:
            # owner 可能因经办人/代理变更而变；同步并在条件回归时重开
            t.owner = d["owner"]
            t.owner_name = d["owner_name"]
            t.related_project_name = d["related_project_name"]
            if t.status == "已完成":
                t.status = "待办"
                t.done_at = ""
                t.done_by = ""

    _complete_orphans(desired, existing)
    db.session.commit()


def _complete_orphans(desired, existing):
    """阶段已推进、不再需要的系统待办自动标记完成（不提交，由调用方提交）。"""
    if existing is None:
        existing = db.session.execute(
            db.select(Todo).where(Todo.source == "system")
        ).scalars().all()
    now = _now()
    for t in existing:
        if t.source_key not in desired and t.status == "待办":
            t.status = "已完成"
            t.done_at = now
            t.done_by = "系统自动"
