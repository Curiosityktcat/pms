# -*- coding: utf-8 -*-
"""官网公告存档接口（只读）。

PMS 2026-06 上线前，院内竞选项目的公告只挂在医院官网。这些公告抓回来存档后，
挂到对应采购项目上，用来查 PMS 上线前那段的挂网时间、开标时间等过程数据。

只读：不提供新增/修改/删除。数据源是官网，要改去官网改，再重抓。
"""
import collections

from flask import Blueprint, request, session, jsonify

from models import db
from models.project import Project
from models.web_announcement import WebAnnouncement
from routes.utils import login_required

bp = Blueprint("web_announcement", __name__, url_prefix="/api/web-announcements")


@bp.route("/meta", methods=["GET"])
@login_required
def meta():
    rows = db.session.execute(db.select(WebAnnouncement)).scalars().all()
    return jsonify({"ok": True, "data": {
        "total": len(rows),
        "types": sorted({r.ann_type for r in rows if r.ann_type}),
        "years": sorted({(r.publish_date or "")[:4] for r in rows
                         if r.publish_date}, reverse=True),
        "officers": sorted({r.officer for r in rows if r.officer}),
        "agencies": sorted({r.agency for r in rows if r.agency}),
        "linked": sum(1 for r in rows if r.project_id),
        "needs_check": sum(1 for r in rows if r.needs_check),
        "date_from": min((r.publish_date for r in rows if r.publish_date), default=""),
        "date_to": max((r.publish_date for r in rows if r.publish_date), default=""),
    }})


@bp.route("", methods=["GET"])
@login_required
def list_ann():
    a = request.args
    conds = []
    if a.get("ann_type"):
        conds.append(WebAnnouncement.ann_type == a["ann_type"])
    if a.get("officer"):
        conds.append(WebAnnouncement.officer == a["officer"])
    if a.get("project_id"):
        conds.append(WebAnnouncement.project_id == int(a["project_id"]))
    if a.get("needs_check") == "1":
        conds.append(WebAnnouncement.needs_check == 1)
    if a.get("year"):
        conds.append(WebAnnouncement.publish_date.like(f"{a['year']}%"))
    if a.get("linked") == "1":
        conds.append(WebAnnouncement.project_id.isnot(None))
    elif a.get("linked") == "0":
        conds.append(WebAnnouncement.project_id.is_(None))

    rows = db.session.execute(
        db.select(WebAnnouncement).where(*conds)
        .order_by(WebAnnouncement.publish_date.desc(), WebAnnouncement.id.desc())
    ).scalars().all()

    kw = (a.get("keyword") or "").strip()
    if kw:
        rows = [r for r in rows if kw in (r.title or "") or kw in (r.project_number or "")
                or kw in (r.project_name or "") or kw in (r.agency or "")]

    # 代理机构只能看自己的项目相关公告
    if session.get("role") == "agency":
        code = session.get("agency_code", "")
        pids = {p.id for p in db.session.execute(
            db.select(Project).filter_by(agency_code=code)).scalars().all()}
        rows = [r for r in rows if r.project_id in pids]

    limit = int(a.get("limit") or 300)
    return jsonify({"ok": True, "total": len(rows),
                    "data": [r.to_dict() for r in rows[:limit]]})


@bp.route("/by-project/<int:pid>", methods=["GET"])
@login_required
def by_project(pid):
    """某项目的全部官网公告，按挂网时间倒序。项目详情页用。"""
    rows = db.session.execute(
        db.select(WebAnnouncement).filter_by(project_id=pid)
        .order_by(WebAnnouncement.publish_date.desc())
    ).scalars().all()
    return jsonify({"ok": True, "data": [r.to_dict() for r in rows]})


@bp.route("/<int:aid>", methods=["GET"])
@login_required
def detail(aid):
    r = db.session.get(WebAnnouncement, aid)
    if not r:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    return jsonify({"ok": True, "data": r.to_dict(with_body=True)})


@bp.route("/counts", methods=["GET"])
@login_required
def counts():
    """每个项目挂了几条公告，列表页一次取回，省得逐条请求。"""
    rows = db.session.execute(
        db.select(WebAnnouncement.project_id, db.func.count(WebAnnouncement.id))
        .where(WebAnnouncement.project_id.isnot(None))
        .group_by(WebAnnouncement.project_id)
    ).all()
    return jsonify({"ok": True, "data": {str(pid): n for pid, n in rows}})


@bp.route("/stats", methods=["GET"])
@login_required
def stats():
    rows = db.session.execute(db.select(WebAnnouncement)).scalars().all()
    by_year = collections.Counter((r.publish_date or "")[:4] for r in rows if r.publish_date)
    by_type = collections.Counter(r.ann_type for r in rows if r.ann_type)
    by_officer = collections.Counter(r.officer for r in rows if r.officer)
    return jsonify({"ok": True, "data": {
        "total": len(rows),
        "linked": sum(1 for r in rows if r.project_id),
        "unlinked": sum(1 for r in rows if not r.project_id),
        "needs_check": sum(1 for r in rows if r.needs_check),
        "by_year": sorted(by_year.items()),
        "by_type": by_type.most_common(),
        "by_officer": by_officer.most_common(),
    }})
