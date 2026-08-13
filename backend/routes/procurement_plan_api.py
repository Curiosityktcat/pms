# -*- coding: utf-8 -*-
"""采购计划池接口：归口科室的年度采购计划，按年度/科室/分类筛选，可与采购项目挂钩。"""
import datetime
import json
import os

from flask import Blueprint, request, session, jsonify, send_file

from models import db
from models.project import Project
from models.procurement_plan import (ProcurementPlan, ProcurementPlanAttachment,
                                     NOT_PROCURED)
from routes.utils import login_required

bp = Blueprint("procurement_plan", __name__, url_prefix="/api/procurement-plans")

UPLOAD_ROOT = "/home/huangxb/pms/uploads/procurement_plan"
ALLOWED = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png",
           ".gif", ".zip", ".rar", ".txt"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _can_edit():
    return session.get("role") in ("officer", "assistant", "leader", "admin")


@bp.route("/meta", methods=["GET"])
@login_required
def meta():
    """筛选项都从真实数据里取，别写死——各科室的分类口径本来就不统一。"""
    rows = db.session.execute(db.select(ProcurementPlan)).scalars().all()

    def uniq(attr):
        return sorted({(getattr(r, attr) or "").strip() for r in rows} - {""})

    return jsonify({"ok": True, "data": {
        "years": sorted({r.year for r in rows if r.year}, reverse=True),
        "depts": uniq("dept"),
        "categories": uniq("category"),
        "categories2": uniq("category2"),
        "methods": uniq("method"),
        "org_forms": uniq("org_form"),
        "statuses": uniq("status"),
        "demand_types": uniq("demand_type"),
        "not_procured": list(NOT_PROCURED),
        "can_edit": _can_edit(),
        "total": len(rows),
    }})


@bp.route("", methods=["GET"])
@login_required
def list_plans():
    a = request.args
    conds = []
    if a.get("year"):
        conds.append(ProcurementPlan.year == int(a["year"]))
    for field in ("dept", "category", "category2", "method", "org_form",
                  "status", "demand_type"):
        if a.get(field):
            conds.append(getattr(ProcurementPlan, field) == a[field])

    rows = db.session.execute(
        db.select(ProcurementPlan).where(*conds)
    ).scalars().all()

    kw = (a.get("keyword") or "").strip()
    if kw:
        rows = [r for r in rows if kw in (r.name or "") or kw in (r.plan_number or "")
                or kw in (r.package_no or "") or kw in (r.note or "")]

    # linked=1 只看已关联项目的，0 只看没关联的
    if a.get("linked") == "1":
        rows = [r for r in rows if r.project_id]
    elif a.get("linked") == "0":
        rows = [r for r in rows if not r.project_id]

    # 默认把「已合并/已集采/延期合并」这类不会走到采购部的藏起来，
    # 它们只是科室台账里的痕迹，混在待立项里会让人误以为还有一堆活没干
    if a.get("include_closed") != "1":
        rows = [r for r in rows if (r.status or "") not in NOT_PROCURED]

    projs = {}
    pids = [r.project_id for r in rows if r.project_id]
    if pids:
        projs = {p.id: p for p in db.session.execute(
            db.select(Project).where(Project.id.in_(pids))).scalars().all()}

    att_count = {}
    for pid, n in db.session.execute(
        db.select(ProcurementPlanAttachment.plan_id,
                  db.func.count(ProcurementPlanAttachment.id))
        .group_by(ProcurementPlanAttachment.plan_id)
    ).all():
        att_count[pid] = n

    out = []
    for r in rows:
        d = r.to_dict(projs.get(r.project_id))
        d["attachment_count"] = att_count.get(r.id, 0)
        out.append(d)
    # 有编号的按编号排，其余按科室+名称，保证顺序稳定
    out.sort(key=lambda d: (not d["plan_number"], d["plan_number"], d["dept"], d["name"]))
    return jsonify({"ok": True, "data": out, "total": len(out)})


@bp.route("/stats", methods=["GET"])
@login_required
def stats():
    """给页面顶部的概览卡片：多少条、多少已立项、多少不会进采购部、预算合计。"""
    year = request.args.get("year")
    conds = [ProcurementPlan.year == int(year)] if year else []
    rows = db.session.execute(db.select(ProcurementPlan).where(*conds)).scalars().all()
    closed = [r for r in rows if (r.status or "") in NOT_PROCURED]
    live = [r for r in rows if r not in closed]
    linked = [r for r in live if r.project_id]
    by_dept = {}
    for r in live:
        k = r.dept or "（未填）"
        by_dept[k] = by_dept.get(k, 0) + 1
    return jsonify({"ok": True, "data": {
        "total": len(rows),
        "live": len(live),
        "closed": len(closed),
        "linked": len(linked),
        "unlinked": len(live) - len(linked),
        "budget_sum": round(sum(r.budget or 0 for r in live), 2),
        "by_dept": sorted(by_dept.items(), key=lambda x: -x[1]),
    }})


@bp.route("/<int:plan_id>", methods=["PUT"])
@login_required
def update_plan(plan_id):
    if not _can_edit():
        return jsonify({"ok": False, "error": "无权修改采购计划"}), 403
    row = db.session.get(ProcurementPlan, plan_id)
    if not row:
        return jsonify({"ok": False, "error": "计划不存在"}), 404
    data = request.get_json(force=True) or {}
    for k in ("name", "package_no", "plan_number", "dept", "demand_dept", "org_form",
              "method", "deadline", "qty", "unit", "category", "category2",
              "demand_type", "status", "note"):
        if k in data:
            setattr(row, k, (data[k] or "").strip() if isinstance(data[k], str) else data[k])
    for k in ("budget", "price_limit"):
        if k in data:
            try:
                setattr(row, k, float(data[k] or 0))
            except (TypeError, ValueError):
                pass
    row.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": row.to_dict()})


@bp.route("/<int:plan_id>/link", methods=["POST"])
@login_required
def link_project(plan_id):
    """把计划挂到正式采购项目上。

    只接受人工点选或按编号定位——名称自动匹配错绑的代价比人工点一下大得多
    （科室写「雾化器【6元版本】」，立项写「2026年气动雾化吸入器采购项目」）。
    """
    if not _can_edit():
        return jsonify({"ok": False, "error": "无权关联项目"}), 403
    row = db.session.get(ProcurementPlan, plan_id)
    if not row:
        return jsonify({"ok": False, "error": "计划不存在"}), 404
    data = request.get_json(force=True) or {}
    pid = data.get("project_id")
    number = (data.get("project_number") or "").strip()

    proj = None
    if pid:
        proj = db.session.get(Project, int(pid))
    elif number:
        proj = db.session.execute(
            db.select(Project).filter_by(number=number)).scalars().first()
    if not proj:
        return jsonify({"ok": False, "error": "找不到该采购项目"}), 404

    other = db.session.execute(db.select(ProcurementPlan).where(
        ProcurementPlan.project_id == proj.id,
        ProcurementPlan.id != plan_id)).scalars().first()
    if other:
        return jsonify({"ok": False,
                        "error": f"该项目已关联计划「{other.name}」，请先解除"}), 400

    row.project_id = proj.id
    row.plan_number = proj.number or row.plan_number
    row.linked_by = session.get("display_name", "")
    row.linked_at = _now()
    row.updated_at = row.linked_at
    db.session.commit()
    return jsonify({"ok": True, "data": row.to_dict(proj), "message": "已关联采购项目"})


@bp.route("/<int:plan_id>/link", methods=["DELETE"])
@login_required
def unlink_project(plan_id):
    if not _can_edit():
        return jsonify({"ok": False, "error": "无权解除关联"}), 403
    row = db.session.get(ProcurementPlan, plan_id)
    if not row:
        return jsonify({"ok": False, "error": "计划不存在"}), 404
    row.project_id = None
    row.linked_by = ""
    row.linked_at = ""
    row.updated_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "message": "已解除关联"})


@bp.route("/<int:plan_id>/candidates", methods=["GET"])
@login_required
def candidates(plan_id):
    """关联时的候选项目：按关键词给提示，只提示不自动绑。"""
    row = db.session.get(ProcurementPlan, plan_id)
    if not row:
        return jsonify({"ok": False, "error": "计划不存在"}), 404
    kw = (request.args.get("keyword") or "").strip()
    taken = {p.project_id for p in db.session.execute(
        db.select(ProcurementPlan).where(ProcurementPlan.project_id.isnot(None))
    ).scalars().all()} - {row.project_id}

    projs = db.session.execute(db.select(Project).where(
        db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
    )).scalars().all()

    def score(p):
        if kw:
            return 1 if (kw in (p.name or "") or kw in (p.number or "")) else 0
        # 没给关键词时，用计划名里的字与项目名的重合度粗排（只做提示）
        name = (row.name or "").strip()
        if not name:
            return 0
        hit = sum(1 for ch in set(name) if ch in (p.name or ""))
        return hit / max(len(set(name)), 1)

    scored = [(score(p), p) for p in projs if p.id not in taken]
    scored = [(s, p) for s, p in scored if s > 0]
    scored.sort(key=lambda x: -x[0])
    return jsonify({"ok": True, "data": [{
        "id": p.id, "number": p.number or "", "name": p.name,
        "status": p.status or "", "officer": p.officer or "",
        "match": round(float(s), 3),
    } for s, p in scored[:30]]})


# ── 附件：科室需求表、办公会决议、报价单等 ─────────────────────────

@bp.route("/<int:plan_id>/attachments", methods=["GET"])
@login_required
def list_attachments(plan_id):
    rows = db.session.execute(
        db.select(ProcurementPlanAttachment).filter_by(plan_id=plan_id)
        .order_by(ProcurementPlanAttachment.id)).scalars().all()
    out = []
    for a in rows:
        d = a.to_dict()
        d["exists"] = bool(a.path and os.path.exists(a.path))
        out.append(d)
    return jsonify({"ok": True, "data": out})


@bp.route("/<int:plan_id>/attachments", methods=["POST"])
@login_required
def upload_attachment(plan_id):
    if not _can_edit():
        return jsonify({"ok": False, "error": "无权上传"}), 403
    plan = db.session.get(ProcurementPlan, plan_id)
    if not plan:
        return jsonify({"ok": False, "error": "计划不存在"}), 404
    files = request.files.getlist("file") or request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "error": "没有收到文件"}), 400

    sub = os.path.join(UPLOAD_ROOT, str(plan_id))
    os.makedirs(sub, exist_ok=True)
    saved = []
    for f in files:
        name = os.path.basename(f.filename or "")
        if not name:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in ALLOWED:
            return jsonify({"ok": False, "error": f"不支持的文件类型：{ext}"}), 400
        row = ProcurementPlanAttachment(
            plan_id=plan_id, filename=name, uploaded_by=session.get("display_name", ""),
            uploaded_at=_now(), source="upload")
        db.session.add(row)
        db.session.flush()                      # 先拿到 id，用它做文件名前缀防重名覆盖
        path = os.path.join(sub, f"{row.id}_{name}")
        f.save(path)
        row.path = path
        row.size = os.path.getsize(path)
        saved.append(row)
    db.session.commit()
    return jsonify({"ok": True, "data": [r.to_dict() for r in saved],
                    "message": f"已上传 {len(saved)} 个文件"})


def _get_att(plan_id, aid):
    return db.session.execute(db.select(ProcurementPlanAttachment)
                              .filter_by(id=aid, plan_id=plan_id)).scalars().first()


@bp.route("/<int:plan_id>/attachments/<int:aid>/preview", methods=["GET"])
@login_required
def preview(plan_id, aid):
    a = _get_att(plan_id, aid)
    if not a or not a.path or not os.path.exists(a.path):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    return send_file(a.path, as_attachment=False, download_name=a.filename)


@bp.route("/<int:plan_id>/attachments/<int:aid>/download", methods=["GET"])
@login_required
def download(plan_id, aid):
    a = _get_att(plan_id, aid)
    if not a or not a.path or not os.path.exists(a.path):
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    return send_file(a.path, as_attachment=True, download_name=a.filename)


@bp.route("/<int:plan_id>/attachments/<int:aid>", methods=["DELETE"])
@login_required
def delete_attachment(plan_id, aid):
    if not _can_edit():
        return jsonify({"ok": False, "error": "无权删除"}), 403
    a = _get_att(plan_id, aid)
    if not a:
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    # 从 WPS 导入的原始资料不删磁盘文件，只解除挂载——那是唯一一份存档
    if a.source == "upload" and a.path and os.path.exists(a.path):
        try:
            os.remove(a.path)
        except OSError:
            pass
    db.session.delete(a)
    db.session.commit()
    return jsonify({"ok": True, "message": "已删除"})
