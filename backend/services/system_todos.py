"""系统事件自动派单：按项目当前所处的节点，给该动手的那一方生成待办，
对方做完（阶段推进）后自动消除，全程不需要任何人手工新建业务。

派单原则——「谁该动手，待办就落在谁头上」：
  代理机构：编制/上传/提交类动作，以及被驳回后的修改
  经办人  ：确认/审核类动作，以及授权函、合同这类采购人方的动作

一个环节的归属不是固定的，而是随单据状态在两方之间来回传递。以采购公告为例：
  无公告/草稿 → 代理「待编制采购公告」
  已提交待确认 → 经办人「待确认采购公告」
  被驳回      → 代理「采购公告被驳回，待修改后重新提交」
  已确认发布   → 本环节待办自动消除，下一环节（是否可开标）落到代理头上

实现：reconcile_system_todos() 算出"此刻应存在的系统待办"（desired），与库中
source='system' 的待办对账——缺则建、已推进则自动完成、条件回归则重开。
幂等键 source_key = sys:{event}:proj{id}:r{round}。
"""
import datetime
import time

from models import db
from models.todo import Todo
from models.project import Project
from models.user import User
from models.announcement import Announcement
from models.procurement_result import ProcurementResult
from models.procurement_round import ProcurementRound
from models.procurement_doc_attachment import ProcurementDocAttachment
from models.auth_letter_record import AuthLetterRecord
from models.contract import Contract
from models.agency_assessment import AgencyAssessment
from services.project_progress import (
    stage_map, AGENCY_TRACK_METHODS, INQUIRY_TRACK_METHODS,
)

# event → (归属方, 标题)。归属方 officer=经办人 / agency=代理机构。
_EVENTS = {
    # 5.1 采购需求
    "demand_confirm":   ("officer", "待确认采购需求（5.1）"),
    "demand_fix":       ("agency",  "采购需求被驳回，待修改后重新提交（5.1）"),
    # 5.2 采购文件
    "doc_upload":       ("agency",  "待上传采购文件（5.2）"),
    "doc_confirm":      ("officer", "待确认采购文件（5.2）"),
    "doc_fix":          ("agency",  "采购文件被驳回，待修改后重新上传（5.2）"),
    # 6.1 采购公告
    "ann_draft":        ("agency",  "待编制采购公告（6.1）"),
    "ann_confirm":      ("officer", "待确认采购公告（6.1）"),
    "ann_fix":          ("agency",  "采购公告被驳回，待修改后重新提交（6.1）"),
    # 6.3 更正公告
    "corr_confirm":     ("officer", "待确认更正公告（6.3）"),
    "corr_fix":         ("agency",  "更正公告被驳回，待修改后重新提交（6.3）"),
    # 开标
    "bid_open":         ("agency",  "待判定是否可开标（开标管理）"),
    "bid_fail_confirm": ("officer", "待确认流标（开标管理）"),
    "auth_letter":      ("officer", "待出具开标授权函（授权函）"),
    # 8.5 项目评审资料
    "review_upload":    ("agency",  "待上传并提交项目评审资料（8.5）"),
    "review_confirm":   ("officer", "待确认项目评审资料（8.5）"),
    "review_fix":       ("agency",  "评审资料被驳回，待补件后重新提交（8.5）"),
    # 9 采购结果
    "result_draft":     ("agency",  "待编制采购结果确认函（9）"),
    "result_confirm":   ("officer", "待确认采购结果（9）"),
    "result_fix":       ("agency",  "采购结果被驳回，待修改后重新提交（9）"),
    "result_recheck":   ("agency",  "采购结果未获确认，待复核后重新推送（9）"),
    # 10 合同：采购结果一确认，活先落到代理机构头上（合同本来就是代理拟的），
    # 代理拟好提交后转经办人审核，形成 代理→经办人 的来回，而不是一直挂在经办人名下
    "contract_draft":   ("agency",  "待拟定合同并提交（10）"),
    "contract_review":  ("officer", "待审核合同并上传盖章件（10）"),
    "contract_fix":     ("agency",  "合同被驳回，待修改后重新提交（10）"),
    "contract":         ("officer", "待签订合同（10）"),   # 非代理轨道（询议价等）由经办人自办
    # 13.4 代理机构考核（项目办结后由经办人完成，对应考核表「采购部对接人签字」）
    "agency_assess":    ("officer", "待完成代理机构服务质量考核（13.4）"),
    # 询/议价、紧急采购轨道
    "inquiry_letter":   ("officer", "待发出询/议价函（7）"),
    "inquiry_review":   ("officer", "待完成询议价/紧急采购评审（8.1）"),
}

# 考核触发判据见 services/assess_ready.py：
# 不再按项目状态判断（定标了但合同没签完就打分，既不公平也算不准归档时效），
# 改为「所有中标包的合同都已上传」才算代理服务交付完毕、可以考核。

# 轮次的中文写法，用于待办标题
_CN_NUM = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六'}

# 已归档的项目不再产生任何流程待办
ARCHIVED_STATUS = "已归档"

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


def _announcement_events(ann, prefix):
    """公告类单据（采购公告 / 更正公告）的状态 → 事件名。

    prefix='ann' 用于 6.1；prefix='corr' 用于 6.3。返回 None 表示本环节无待办。
    """
    if ann is None:
        return f"{prefix}_draft" if prefix == "ann" else None
    st = ann.status or "草稿"
    if st == "已确认":
        return None
    if st == "已驳回":
        return f"{prefix}_fix"
    if st == "待确认":
        return f"{prefix}_confirm"
    # 草稿
    return f"{prefix}_draft" if prefix == "ann" else None


def _collect(p, meta, ctx):
    """算出某个项目此刻应该存在哪些事件。返回 [event, ...]。"""
    stage = meta.get("current_stage", "")
    rnd_no = meta.get("current_round", 1) or 1
    pending_contract = meta.get("pending_contract", 0)
    method = p.method or ""
    events = []

    # ── 询/议价、紧急采购：独立轨道，不走轮次系统 ──────────────────
    if method in INQUIRY_TRACK_METHODS:
        if stage == "inquiry":
            events.append("inquiry_letter")
        elif stage == "review":
            events.append("inquiry_review")
        elif stage == "contract":
            events.append("contract")
        return events

    agency_track = method in AGENCY_TRACK_METHODS
    rnd = ctx["rounds"].get((p.id, rnd_no))

    if stage == "demand_confirm":
        if rnd is not None and (rnd.demand_reject_reason or ""):
            events.append("demand_fix" if agency_track else "demand_confirm")
        else:
            events.append("demand_confirm")

    elif stage == "doc_confirm":
        if rnd is not None and (rnd.doc_reject_reason or ""):
            events.append("doc_fix")
        elif agency_track and (p.id, rnd_no) not in ctx["doc_uploaded"]:
            events.append("doc_upload")
        else:
            events.append("doc_confirm")

    elif stage == "announce":
        ev = _announcement_events(ctx["ann"].get((p.id, rnd_no)), "ann")
        if ev:
            events.append(ev)

    elif stage == "bid_open":
        # 代理已提交流标、等经办人拍板 → 待办转给经办人
        if rnd is not None and rnd.can_open == "流标" and rnd.can_open_status == "待确认":
            events.append("bid_fail_confirm")
        else:
            events.append("bid_open")

    elif stage == "result":
        # 8.5 评审资料先过，再谈 9 采购结果
        rv = (rnd.review_status if rnd is not None else "") or ""
        has_att = (p.id, rnd_no) in ctx["review_uploaded"]
        if agency_track and rv != "已确认":
            if rv == "已驳回":
                events.append("review_fix")
            elif rv == "待确认":
                events.append("review_confirm")
            else:
                events.append("review_upload" if not has_att or rv == "" else "review_confirm")
        else:
            res = ctx["result"].get((p.id, rnd_no))
            st = (res.status if res is not None else "") or ""
            if res is None or st == "草稿":
                events.append("result_draft")
            elif st == "已驳回":
                events.append("result_fix")
            elif st == "不确认":
                events.append("result_recheck")
            elif st == "待确认":
                events.append("result_confirm")

    # ── 与阶段无关的并行事项 ──────────────────────────────────────
    # 授权函：本轮已确认可开标、但尚未出具授权函
    if (agency_track and rnd is not None
            and rnd.can_open == "可开标" and rnd.can_open_status == "已确认"
            and (p.id, rnd_no) not in ctx["auth_letters"]):
        events.append("auth_letter")

    # 更正公告：任何轮次只要有待确认/被驳回的更正公告，就该有人处理
    ev = _announcement_events(ctx["corr"].get((p.id, rnd_no)), "corr")
    if ev:
        events.append(ev)

    # 合同：有已中标未签订的包时，按合同当前状态决定该谁动手
    if pending_contract > 0:
        if p.id in ctx["contract_rejected"]:
            events.append("contract_fix")          # 被驳回 → 代理改
        elif not (p.agency_code or ""):
            events.append("contract")              # 没有代理（询议价等）→ 经办人自办
        elif p.id in ctx["contract_pending_review"]:
            events.append("contract_review")       # 代理已提交 → 经办人审核并传盖章件
        else:
            events.append("contract_draft")        # 还没拟或仍是草案 → 代理拟

    # 代理机构考核：所有中标包的合同都上传完了 = 代理的活全干完了，该由经办人打分。
    # 提交考核后本条自动消除；撤回考核会重新出现。
    if ((p.agency_code or "")
            and p.id in ctx["assess_ready"]
            and p.id not in ctx["assessed"]):
        events.append("agency_assess")

    return events


def load_ctx(pids):
    """一次性载入派单判定要用的全部单据（避免逐项目 N+1）。

    与「当前处理人」共用：services/pending_owner.py 也调这个，
    保证待办里的归属方与各页面显示的当前处理人出自同一批数据。
    """
    # ── 一次性把判定要用的单据全量载入，避免逐项目 N+1 ────────────
    doc_uploaded = set()
    review_uploaded = set()
    for a in db.session.execute(
        db.select(ProcurementDocAttachment).where(
            ProcurementDocAttachment.kind.in_(("doc", "review_result")))
    ).scalars().all():
        key = (a.project_id, a.round_number or 1)
        (doc_uploaded if a.kind == "doc" else review_uploaded).add(key)

    rounds = {(r.project_id, r.round_number or 1): r for r in db.session.execute(
        db.select(ProcurementRound).where(ProcurementRound.project_id.in_(pids))
    ).scalars().all()}

    # 每个 (项目, 轮次) 取最新一条公告 / 更正公告 / 采购结果
    ann_map, corr_map = {}, {}
    for a in db.session.execute(
        db.select(Announcement).where(Announcement.project_id.in_(pids))
        .order_by(Announcement.id)
    ).scalars().all():
        key = (a.project_id, a.round_number or 1)
        if a.ann_type == "correction":
            # 更正公告：已确认的不占位，未了结的才要人处理
            if (a.status or "") != "已确认":
                corr_map[key] = a
        elif a.ann_type == "procurement":
            ann_map[key] = a

    result_map = {}
    for r in db.session.execute(
        db.select(ProcurementResult).where(ProcurementResult.project_id.in_(pids))
        .order_by(ProcurementResult.id)
    ).scalars().all():
        result_map[(r.project_id, r.round_number or 1)] = r

    auth_letters = {(a.project_id, a.round_number or 1) for a in db.session.execute(
        db.select(AuthLetterRecord).where(AuthLetterRecord.project_id.in_(pids))
    ).scalars().all()}

    all_contracts = db.session.execute(
        db.select(Contract).where(Contract.project_id.in_(pids))
    ).scalars().all()
    contract_rejected = {c.project_id for c in all_contracts
                         if (c.reject_reason or "") and c.status == "合同草案"}
    # 代理已提交、等经办人审核并上传盖章件的项目
    contract_pending_review = {c.project_id for c in all_contracts
                               if c.status == "审核完成"}

    # 所有中标包合同均已上传的项目 = 可以开始考核
    from services.assess_ready import ready_project_ids
    assess_ready = ready_project_ids(pids)

    # 已提交考核的项目——考核一提交，对应待办就自动消除
    assessed = {a.project_id for a in db.session.execute(
        db.select(AgencyAssessment).where(AgencyAssessment.project_id.in_(pids))
    ).scalars().all() if a.status == "已提交"}

    ctx = {
        "doc_uploaded": doc_uploaded, "review_uploaded": review_uploaded,
        "rounds": rounds, "ann": ann_map, "corr": corr_map, "result": result_map,
        "auth_letters": auth_letters, "contract_rejected": contract_rejected,
        "contract_pending_review": contract_pending_review,
        "assessed": assessed,
        "assess_ready": assess_ready,
    }
    return ctx


def reconcile_system_todos():
    projects = db.session.execute(
        db.select(Project).where(
            db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
            db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
            # 已归档 = 这个项目彻底办完了，不该再往任何人待办里塞东西。
            # 尤其是导入的历史存量项目：服务启动时的存量回填会给它们补出
            # 采购轮次骨架，阶段就被算成「待确认采购需求」，
            # 一下子往待办里灌进上百条早就办完的活（踩过一次，91 个项目灌了 100 条）。
            db.or_(Project.status != ARCHIVED_STATUS, Project.status.is_(None)),
        )
    ).scalars().all()
    if not projects:
        _complete_orphans({}, None)
        db.session.commit()
        return

    pids = [p.id for p in projects]
    info = stage_map(pids)

    users = db.session.execute(db.select(User).where(User.active == 1)).scalars().all()
    users_by_username = {u.username: u for u in users}
    users_by_display = {u.display_name: u for u in users if u.display_name}
    agency_by_code = {u.agency_code: u for u in users
                      if u.role == "agency" and u.agency_code}

    ctx = load_ctx(pids)

    desired = {}
    for p in projects:
        meta = info.get(p.id) or {}
        rnd_no = meta.get("current_round", 1) or 1
        for event in _collect(p, meta, ctx):
            role, title = _EVENTS[event]
            if role == "officer":
                who = _resolve_officer(p.officer, users_by_username, users_by_display)
            else:
                u = agency_by_code.get(p.agency_code or "")
                who = (u.username, u.display_name or u.username) if u else None
            if not who:
                continue
            owner, owner_name = who
            key = f"sys:{event}:proj{p.id}:r{rnd_no}"
            # 多轮项目（流标/废标重招）每一轮都要单独出授权函，
            # 标题不带轮次的话，第二轮的待办看着和第一轮一模一样，
            # 人会以为"这活我不是干过了吗"——所以把第几次开标写进标题
            shown = title
            if rnd_no and rnd_no > 1 and event in (
                    "auth_letter", "bid_open", "bid_fail_confirm",
                    "ann_draft", "ann_confirm", "ann_fix"):
                shown = f"{title}·第{_CN_NUM.get(rnd_no, rnd_no)}次采购"
            desired[key] = {
                "owner": owner, "owner_name": owner_name,
                "title": shown,
                # 被驳回类待办优先级提到紧急——这类是卡住流程的返工
                "priority": "紧急" if event.endswith("_fix") or event == "result_recheck" else "重要",
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
                status="待办", priority=d["priority"],
                related_project_id=d["related_project_id"],
                related_project_name=d["related_project_name"],
                created_by="system", created_by_name="系统",
                created_at=now, source="system", source_key=key,
            ))
        else:
            # owner 可能因经办人/代理变更而变；同步并在条件回归时重开
            t.owner = d["owner"]
            t.owner_name = d["owner_name"]
            t.title = d["title"]
            t.priority = d["priority"]
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
