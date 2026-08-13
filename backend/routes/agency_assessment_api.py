"""代理机构服务质量考核 —— /api/agency-assessments

一个项目一份考核表。采购部对接人打分，系统对 6 个可量化项给出建议分
（时效靠时间戳、规范性靠驳回留痕），人可覆盖。提交后进入代理机构的
累计分汇总，按考核办法给出「暂停拟派 / 提前拟派 / 暂停资格」的处置建议。
"""
import datetime
import json

from flask import Blueprint, request, session, jsonify

from models import db
from models.agency_assessment import AgencyAssessment
from models.project import Project
from models.agency import Agency
from routes.utils import login_required, can_view_project
from services.permission import is_admin_user
from services import agency_assessment as svc

bp = Blueprint("agency_assessment", __name__, url_prefix="/api/agency-assessments")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _can_assess():
    """考核由采购人方做——代理机构不能给自己打分。"""
    return (session.get("role", "") in ("officer", "assistant", "pd_assistant", "leader")
            or is_admin_user(session.get("user", "")))


def _is_owner_officer(project) -> bool:
    """本项目的经办人本人。考核表末尾要「采购部对接人签字」，对接人就是经办人。"""
    return (project.officer or "") == session.get("display_name", "")


def _can_assess_project(project):
    """谁能给这个项目的代理机构打分。

    主责是本项目经办人——是他全程跟的项目，只有他说得清代理干得怎么样。
    负责人/助理/管理员保留权限做兜底（经办人离职、休假或需要复核时），
    但待办只派给经办人，不让所有人都收到。
    返回 (ok, 错误信息)。
    """
    if not _can_assess():
        return False, "仅采购人方可考核代理机构"
    if session.get("role", "") == "officer" and not _is_owner_officer(project):
        return False, "只能考核自己经办的项目"
    return True, ""


def _agency_name(code):
    if not code:
        return ""
    a = db.session.execute(db.select(Agency).filter_by(code=code)).scalar_one_or_none()
    return a.name if a else code


@bp.route("/meta", methods=["GET"])
@login_required
def meta():
    """评分表定义：15 个评分项 + 9 条一票否决 + 主观项选项 + 阈值。"""
    return jsonify({"ok": True, "data": {
        "items": svc.ITEMS,
        "veto_items": svc.VETO_ITEMS,
        "subj_options": list(svc.SUBJ_OPTIONS),
        "thresholds": {
            "pass_line": svc.PASS_LINE,
            "bonus_line": svc.BONUS_LINE,
            "suspend_line": svc.SUSPEND_LINE,
            "valid_months": svc.VALID_MONTHS,
        },
        "can_assess": _can_assess(),
    }})


@bp.route("", methods=["GET"])
@login_required
def list_assessments():
    """考核列表。代理机构只看得到自己的，且只看已提交的（不看别人怎么被打分）。"""
    role = session.get("role", "")
    conds = []
    if role == "agency":
        conds.append(AgencyAssessment.agency_code == session.get("agency_code", ""))
        conds.append(AgencyAssessment.status == "已提交")
    if request.args.get("agency_code"):
        conds.append(AgencyAssessment.agency_code == request.args["agency_code"])
    if request.args.get("status"):
        conds.append(AgencyAssessment.status == request.args["status"])
    # 起止月份筛选，和机构汇总用同一套解析，两边口径保持一致
    lo, hi = svc.month_range(request.args.get("start"), request.args.get("end"))
    if lo:
        conds.append(AgencyAssessment.assessed_at >= lo)
    if hi:
        conds.append(AgencyAssessment.assessed_at < hi)
    rows = db.session.execute(
        db.select(AgencyAssessment).where(*conds).order_by(AgencyAssessment.id.desc())
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/pending-projects", methods=["GET"])
@login_required
def pending_projects():
    """可发起考核的项目：走代理的、已到合同/归档阶段、且还没考核过的。"""
    if not _can_assess():
        return jsonify({"ok": True, "data": []})
    done = {a.project_id for a in db.session.execute(
        db.select(AgencyAssessment)).scalars().all()}
    rows = db.session.execute(db.select(Project).where(
        db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
        Project.agency_code != "",
    )).scalars().all()
    from services.assess_ready import ready_project_ids
    ready = ready_project_ids([p.id for p in rows])

    out = []
    me = session.get("display_name", "")
    for p in rows:
        if p.id in done:
            continue
        if session.get("role") == "officer" and p.officer != me:
            continue
        # 触发条件：所有中标包的合同都已上传（= 代理的活全干完）
        if p.id not in ready:
            continue
        out.append({
            "id": p.id, "number": p.number, "name": p.name,
            "method": p.method, "officer": p.officer,
            "agency_code": p.agency_code, "agency_name": _agency_name(p.agency_code),
            "status": p.status,
        })
    return jsonify({"ok": True, "data": out})


@bp.route("/project/<int:pid>", methods=["GET"])
@login_required
def get_by_project(pid):
    """取某项目的考核表：已有则回填，没有则给一份带自动建议分的空表。"""
    project = db.session.get(Project, pid)
    if not project or not can_view_project(project):
        return jsonify({"ok": False, "error": "项目不存在或无权访问"}), 404
    row = db.session.execute(
        db.select(AgencyAssessment).filter_by(project_id=pid)).scalars().first()
    saved = None
    if row:
        try:
            saved = json.loads(row.items_json or "[]")
        except Exception:
            saved = None
    # 代理机构只能看自己项目、且只看已提交的定稿，看不到草稿也改不了
    if session.get("role") == "agency":
        if (project.agency_code or "") != session.get("agency_code", ""):
            return jsonify({"ok": False, "error": "无权查看"}), 403
        if not row or row.status != "已提交":
            return jsonify({"ok": False, "error": "该项目考核尚未完成，暂不可查看"}), 404

    items = svc.build_items(project, saved)
    data = row.to_dict() if row else {
        "id": None, "project_id": pid,
        "project_number": project.number, "project_name": project.name,
        "agency_code": project.agency_code,
        "agency_name": _agency_name(project.agency_code),
        "veto": [], "veto_note": "",
        # 综合评价给默认值「满意」——大多数项目本就正常，让人只改例外的那几项，
        # 而不是每次从空白开始逐个勾
        "subj_timeliness": svc.SUBJ_DEFAULT,
        "subj_ability": svc.SUBJ_DEFAULT,
        "subj_attitude": svc.SUBJ_DEFAULT,
        "comment": "", "status": "草稿",
    }
    data["readonly"] = session.get("role") == "agency"
    data["items"] = items
    data["total_score"] = svc.total_of(items)
    return jsonify({"ok": True, "data": data})


def _apply(row, data, project):
    items = data.get("items") or []
    row.items_json = svc.dump_items(items)
    # 总分服务端算，不信前端传来的数
    full = svc.build_items(project, items)
    row.total_score = svc.total_of(full)

    veto = [v for v in (data.get("veto") or []) if v in {x["key"] for x in svc.VETO_ITEMS}]
    row.veto_json = json.dumps(veto, ensure_ascii=False)
    row.veto_hit = 1 if veto else 0
    row.veto_note = (data.get("veto_note") or "").strip()

    for f in ("subj_timeliness", "subj_ability", "subj_attitude"):
        v = data.get(f) or ""
        setattr(row, f, v if v in svc.SUBJ_OPTIONS else "")
    row.comment = (data.get("comment") or "").strip()
    row.updated_at = _now()


@bp.route("/project/<int:pid>", methods=["POST"])
@login_required
def save_by_project(pid):
    """保存/提交考核。?submit=1 表示提交定稿。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    ok, err = _can_assess_project(project)
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    if not project.agency_code:
        return jsonify({"ok": False, "error": "该项目没有代理机构，无需考核"}), 400

    data = request.get_json(silent=True) or {}
    row = db.session.execute(
        db.select(AgencyAssessment).filter_by(project_id=pid)).scalars().first()
    if row and row.status == "已提交" and not data.get("force"):
        return jsonify({"ok": False, "error": "该项目考核已提交，如需修改请先撤回"}), 400
    if row is None:
        row = AgencyAssessment(
            project_id=pid, project_number=project.number, project_name=project.name,
            agency_code=project.agency_code, agency_name=_agency_name(project.agency_code),
            created_by=session.get("display_name", ""), created_at=_now(),
        )
        db.session.add(row)

    _apply(row, data, project)
    if request.args.get("submit") == "1":
        row.status = "已提交"
        row.assessor = session.get("display_name", "")
        row.assessed_at = _now()
    db.session.commit()

    out = row.to_dict()
    out["summary"] = svc.agency_summary(row.agency_code)
    return jsonify({"ok": True, "data": out,
                    "message": "已提交考核" if row.status == "已提交" else "已保存"})


@bp.route("/<int:aid>/revoke", methods=["POST"])
@login_required
def revoke(aid):
    row = db.session.get(AgencyAssessment, aid)
    if not row:
        return jsonify({"ok": False, "error": "考核不存在"}), 404
    project = db.session.get(Project, row.project_id)
    ok, err = _can_assess_project(project) if project else (_can_assess(), "权限不足")
    if not ok:
        return jsonify({"ok": False, "error": err}), 403
    row.status = "草稿"
    row.assessed_at = ""
    row.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤回为草稿"})


@bp.route("/summary", methods=["GET"])
@login_required
def summary():
    """各代理机构的累计考核汇总 + 处置建议（暂停拟派 / 提前拟派 / 暂停资格）。

    默认按考核办法看「近 3 个月」；带 start/end（`2026-01` 这种月份）就看指定区间，
    统计「2026 年以来」「1 到 6 月各家表现」用后者。
    """
    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()
    codes = [a.code for a in db.session.execute(db.select(Agency)).scalars().all()]
    if session.get("role") == "agency":
        codes = [session.get("agency_code", "")]
    name_of = {a.code: a.name for a in db.session.execute(db.select(Agency)).scalars().all()}
    out = []
    for c in codes:
        if not c:
            continue
        s = svc.agency_summary(c, start=start, end=end)
        s["agency_name"] = name_of.get(c, c)
        out.append(s)
    out.sort(key=lambda x: (x["count"] == 0, -(x["net"] or 0)))
    return jsonify({"ok": True, "data": out,
                    "period": (out[0]["period"] if out else ""),
                    "range": {"start": start, "end": end}})
