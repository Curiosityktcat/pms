"""法规库 API：列表/筛选/详情（只读）。"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, func
from models import db
from models.law import Law
from routes.utils import login_required

bp = Blueprint("law", __name__, url_prefix="/api/laws")


@bp.get("")
@login_required
def list_laws():
    kw = (request.args.get("keyword") or "").strip()
    level = (request.args.get("level") or "").strip()
    region = (request.args.get("region") or "").strip()
    timeliness = (request.args.get("timeliness") or "").strip()
    catalog_only = request.args.get("catalog_only") in ("1", "true", "True")
    page = max(int(request.args.get("page") or 1), 1)
    page_size = min(max(int(request.args.get("page_size") or 20), 1), 100)

    q = Law.query
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(Law.title.like(like), Law.law_number.like(like),
                         Law.full_text.like(like), Law.issue_unit.like(like)))
    if level:
        q = q.filter(Law.level == level)
    if region:
        q = q.filter(Law.region == region)
    if timeliness:
        q = q.filter(Law.timeliness == timeliness)
    if catalog_only:
        q = q.filter(Law.catalog_num.isnot(None))

    total = q.count()
    # 汇编目录项按序号排，其余按层次+标题
    q = q.order_by(Law.catalog_num.is_(None), Law.catalog_num.asc(),
                   Law.level.asc(), Law.title.asc())
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"ok": True, "items": [r.to_dict() for r in rows],
                    "total": total, "page": page, "page_size": page_size})


@bp.get("/levels")
@login_required
def levels():
    rows = (db.session.query(Law.level, func.count(Law.id))
            .group_by(Law.level).order_by(func.count(Law.id).desc()).all())
    data = [{"level": lv or "未分类", "count": n} for lv, n in rows]
    total = db.session.query(func.count(Law.id)).scalar() or 0
    catalog_n = db.session.query(func.count(Law.id)).filter(Law.catalog_num.isnot(None)).scalar() or 0
    return jsonify({"ok": True, "levels": data, "total": total, "catalog_total": catalog_n})


@bp.get("/<int:law_id>")
@login_required
def detail(law_id):
    law = Law.query.get(law_id)
    if not law:
        return jsonify({"ok": False, "msg": "未找到"}), 404
    return jsonify({"ok": True, "data": law.to_dict(full=True)})
