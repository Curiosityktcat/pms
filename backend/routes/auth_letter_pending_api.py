"""待出具授权函清单  —  /api/auth-letter/pending

挂网并确认可开标后，这一轮就需要一份开标授权函。原来只能靠人自己去
「授权函」页里翻项目下拉框找，容易漏、也容易重复做——尤其项目流标重招后
进入第二轮，第二轮要重新出一份，但项目名和第一轮一模一样，很容易以为
"这活我干过了"。

所以这里直接把「哪个项目、第几次开标、还没出授权函」列成任务清单，
前端渲染成卡片，点一下就进入该项目该轮次的授权函生成。
"""
from flask import Blueprint, session, jsonify

from models import db
from models.project import Project
from models.procurement_round import ProcurementRound
from models.auth_letter_record import AuthLetterRecord
from models.announcement import Announcement
from routes.utils import login_required
from services.permission import is_admin_user
from services.project_progress import AGENCY_TRACK_METHODS

bp = Blueprint("auth_letter_pending", __name__, url_prefix="/api/auth-letter")

CN = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六"}


def _visible(p) -> bool:
    role = session.get("role", "")
    if role == "agency":
        return (p.agency_code or "") == session.get("agency_code", "")
    if role == "officer":
        return (p.officer or "") == session.get("display_name", "")
    return role in ("assistant", "pd_assistant", "leader") or is_admin_user(session.get("user", ""))


@bp.route("/pending", methods=["GET"])
@login_required
def pending():
    """列出「已确认可开标、但本轮还没出授权函」的项目轮次。"""
    projects = db.session.execute(db.select(Project).where(
        db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
    )).scalars().all()
    pmap = {p.id: p for p in projects if _visible(p)}
    if not pmap:
        return jsonify({"ok": True, "data": []})
    pids = list(pmap)

    # 已出过授权函的 (项目, 轮次)
    done = {(a.project_id, a.round_number or 1) for a in db.session.execute(
        db.select(AuthLetterRecord).where(AuthLetterRecord.project_id.in_(pids))
    ).scalars().all()}

    # 每轮的开标时间取该轮采购公告的响应截止时间，没有就退回项目的 bid_time
    ann = {}
    for a in db.session.execute(db.select(Announcement).where(
        Announcement.project_id.in_(pids), Announcement.ann_type == "procurement"
    )).scalars().all():
        if a.status == "已确认":
            ann[(a.project_id, a.round_number or 1)] = a.response_deadline or ""

    out = []
    for r in db.session.execute(db.select(ProcurementRound).where(
        ProcurementRound.project_id.in_(pids)
    )).scalars().all():
        p = pmap.get(r.project_id)
        if p is None or (p.method or "") not in AGENCY_TRACK_METHODS:
            continue
        # 只有「确认可开标」的轮次才需要授权函；流标的不需要
        if r.can_open != "可开标" or r.can_open_status != "已确认":
            continue
        rn = r.round_number or 1
        if (p.id, rn) in done:
            continue
        out.append({
            "project_id": p.id,
            "number": p.number or "",
            "name": p.name or "",
            "round_number": rn,
            "round_cn": f"第{CN.get(rn, rn)}次",
            "officer": p.officer or "",
            "agency_code": p.agency_code or "",
            "method": p.method or "",
            "bid_time": ann.get((p.id, rn)) or p.bid_time or "",
            "confirmed_at": r.can_open_at or "",
        })
    # 开标时间近的排前面（空的排最后）
    out.sort(key=lambda x: (not x["bid_time"], x["bid_time"]))
    return jsonify({"ok": True, "data": out})


@bp.route("/done", methods=["GET"])
@login_required
def done_list():
    """已出具的授权函记录，供核对「这一轮到底做没做」。"""
    projects = {p.id: p for p in db.session.execute(db.select(Project)).scalars().all()
                if _visible(p)}
    rows = db.session.execute(
        db.select(AuthLetterRecord).order_by(AuthLetterRecord.id.desc())
    ).scalars().all()
    out = []
    for a in rows:
        p = projects.get(a.project_id)
        if p is None:
            continue
        rn = a.round_number or 1
        out.append({
            "id": a.id, "project_id": a.project_id,
            "number": a.project_number or (p.number or ""),
            "name": a.project_name or (p.name or ""),
            "round_number": rn, "round_cn": f"第{CN.get(rn, rn)}次",
            "bid_time": a.bid_time or "",
            "supervisor_name": a.supervisor_name or "",
            "representative_names": a.representative_names or "",
            "generated_by": a.generated_by or "",
            "generated_at": a.generated_at or "",
        })
    return jsonify({"ok": True, "data": out[:200]})
