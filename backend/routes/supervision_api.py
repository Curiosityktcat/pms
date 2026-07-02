"""监督投诉库 API：全国政府采购质疑/投诉受理 与 公共资源交易行政监督 渠道（只读，支持关键字搜索）。"""
from flask import Blueprint, request, jsonify
from sqlalchemy import or_, func
from models import db
from models.supervision import SupervisionChannel as SC
from routes.utils import login_required

bp = Blueprint("supervision", __name__, url_prefix="/api/supervision")


@bp.get("")
@login_required
def list_channels():
    kw = (request.args.get("keyword") or "").strip()
    region = (request.args.get("region") or "").strip()
    level = (request.args.get("level") or "").strip()
    org_type = (request.args.get("org_type") or "").strip()
    page = max(int(request.args.get("page") or 1), 1)
    page_size = min(max(int(request.args.get("page_size") or 20), 1), 200)

    q = SC.query
    if kw:
        like = f"%{kw}%"
        q = q.filter(or_(SC.region.like(like), SC.region_full.like(like),
                         SC.name.like(like), SC.url.like(like),
                         SC.channel.like(like), SC.org_type.like(like),
                         SC.page_title.like(like)))
    if region:
        q = q.filter(SC.region == region)
    if level:
        q = q.filter(SC.level == level)
    if org_type:
        q = q.filter(SC.org_type == org_type)

    total = q.count()
    q = q.order_by(SC.level.asc(), SC.region.asc(), SC.org_type.asc(), SC.id.asc())
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return jsonify({"ok": True, "items": [r.to_dict() for r in rows],
                    "total": total, "page": page, "page_size": page_size})


@bp.get("/filters")
@login_required
def filters():
    def grouped(col):
        rows = (db.session.query(col, func.count(SC.id))
                .group_by(col).order_by(func.count(SC.id).desc()).all())
        return [{"value": v or "未分类", "count": n} for v, n in rows]

    total = db.session.query(func.count(SC.id)).scalar() or 0
    alive = db.session.query(func.count(SC.id)).filter(SC.http_status == 200).scalar() or 0
    regions = [r[0] for r in db.session.query(SC.region).distinct().order_by(SC.region.asc()).all() if r[0]]
    return jsonify({"ok": True, "total": total, "alive": alive,
                    "regions": regions,
                    "org_types": grouped(SC.org_type),
                    "levels": grouped(SC.level)})


@bp.get("/<int:cid>")
@login_required
def detail(cid):
    row = SC.query.get(cid)
    if not row:
        return jsonify({"ok": False, "msg": "未找到"}), 404
    return jsonify({"ok": True, "data": row.to_dict()})
