# -*- coding: utf-8 -*-
"""采购公告 → 医院官网挂网的接口层。

PMS 里点「确认发布」后，这边把公告推到官网（填报→审核→生成列表页），
成功后把公网网址回写到公告上；撤回则把官网那条删掉。
官网操作慢（生成列表页要几十秒），所以走后台线程，前端轮询状态。
"""
import datetime
import threading

from flask import Blueprint, jsonify, request, session

from models import db
from models.announcement import Announcement
from models.project import Project
from routes.utils import login_required
from services import njyy_portal as portal

bp = Blueprint("njyy_portal", __name__, url_prefix="/api/announcements")

# 正在跑的挂网任务：ann_id → 线程，避免同一条公告被点两次
_running = {}
_running_lock = threading.Lock()


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def portal_dict(ann):
    """给前端的挂网信息（挂网管理面板用）。"""
    return {
        "portal_status": ann.portal_status or "",
        "portal_url": ann.portal_url or "",
        "portal_news_id": ann.portal_news_id or 0,
        "portal_error": ann.portal_error or "",
        "portal_at": ann.portal_at or "",
    }


def _title_for(project, ann):
    """官网标题：与人工挂的那条保持一致——医院全称 + 项目名(第X次) + 公告类型。"""
    from services.announcement import _round_cn
    name = (project.name or "").strip()
    rn = ann.round_number or 1
    if rn > 1:
        name += "（第%s次）" % _round_cn(rn)
    kind = {"procurement": "院内竞选公告",
            "correction": "更正公告",
            "survey": "征求意见公告",
            "single_source": "单一来源公示"}.get(ann.ann_type, "公告")
    return "内江市第一人民医院%s%s" % (name, kind)


def _payload(app, aid):
    """在应用上下文里备好挂网要用的标题/正文/附件（线程里先拿干净的数据）。"""
    from routes.announcement_api import _generate_word_buf, _get_agency_name, UPLOAD_ROOT
    from models.announcement_attachment import AnnouncementAttachment
    import os

    ann = db.session.get(Announcement, aid)
    project = db.session.get(Project, ann.project_id)
    agency_name = _get_agency_name(project.agency_code) if project else ""
    buf, filename = _generate_word_buf(project, ann, agency_name)
    blob = buf.getvalue()
    html = portal.docx_to_html(blob)

    files = [(filename, blob)]        # 公告正文 Word 本身也作为附件挂上去
    rows = db.session.execute(
        db.select(AnnouncementAttachment).filter_by(announcement_id=aid)
    ).scalars().all()
    for a in rows:
        p = os.path.join(UPLOAD_ROOT, str(aid), a.saved_name or "")
        if a.saved_name and os.path.exists(p):
            with open(p, "rb") as f:
                files.append((a.original_name or a.saved_name, f.read()))
    return _title_for(project, ann), html, files


def _run_publish(app, aid, actor):
    with app.app_context():
        try:
            title, html, files = _payload(app, aid)
            res = portal.publish(title, html, files)
            ann = db.session.get(Announcement, aid)
            ann.portal_news_id = res["news_id"]
            ann.portal_url = res["url"]
            ann.portal_status = "已挂网" if res.get("verified") else "已挂网待复核"
            ann.portal_error = ""
            ann.portal_at = _now()
            db.session.commit()
            _log(aid, "portal_publish", f"{actor} 挂网成功 {res['url']}")
        except Exception as e:                       # noqa: BLE001
            db.session.rollback()
            ann = db.session.get(Announcement, aid)
            if ann:
                ann.portal_status = "挂网失败"
                ann.portal_error = str(e)[:400]
                ann.portal_at = _now()
                db.session.commit()
            _log(aid, "portal_publish_fail", str(e)[:200])
        finally:
            with _running_lock:
                _running.pop(aid, None)


def _run_revoke(app, aid, actor):
    with app.app_context():
        ann = db.session.get(Announcement, aid)
        nid = ann.portal_news_id if ann else 0
        try:
            portal.revoke(int(nid))
            ann = db.session.get(Announcement, aid)
            ann.portal_status = "已撤网"
            ann.portal_url = ""
            ann.portal_news_id = 0
            ann.portal_error = ""
            ann.portal_at = _now()
            db.session.commit()
            _log(aid, "portal_revoke", f"{actor} 已从官网撤下 id={nid}")
        except Exception as e:                       # noqa: BLE001
            db.session.rollback()
            ann = db.session.get(Announcement, aid)
            if ann:
                ann.portal_status = "撤网失败"
                ann.portal_error = str(e)[:400]
                ann.portal_at = _now()
                db.session.commit()
            _log(aid, "portal_revoke_fail", str(e)[:200])
        finally:
            with _running_lock:
                _running.pop(aid, None)


def _log(aid, action, note):
    try:
        from services import approval_log as alog
        ann = db.session.get(Announcement, aid)
        if ann:
            alog.log(ann.project_id, "announcement", action,
                     round_number=ann.round_number or 1, target_id=aid, reason=note)
            db.session.commit()
    except Exception:
        db.session.rollback()


def start_publish(app, ann, actor=""):
    """确认发布后由公告接口调用：后台线程推官网。已在跑的不重复推。"""
    if not portal.enabled():
        return False
    with _running_lock:
        if ann.id in _running:
            return False
        ann.portal_status = "挂网中"
        ann.portal_error = ""
        ann.portal_at = _now()
        db.session.commit()
        t = threading.Thread(target=_run_publish, args=(app, ann.id, actor), daemon=True)
        _running[ann.id] = t
        t.start()
    return True


def start_revoke(app, ann, actor=""):
    """撤回确认时调用：把官网那条删掉。没挂过就什么都不做。"""
    if not portal.enabled() or not (ann.portal_news_id or 0):
        return False
    with _running_lock:
        if ann.id in _running:
            return False
        ann.portal_status = "撤网中"
        ann.portal_error = ""
        db.session.commit()
        t = threading.Thread(target=_run_revoke, args=(app, ann.id, actor), daemon=True)
        _running[ann.id] = t
        t.start()
    return True


# ── 手动接口（挂网管理面板里的按钮）──────────────────────────────
def _guard(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return None, (jsonify({"ok": False, "error": "公告不存在"}), 404)
    project = db.session.get(Project, ann.project_id)
    from routes.announcement_api import _can_confirm
    if not _can_confirm(project):
        return None, (jsonify({"ok": False, "error": "仅本项目经办人或负责人可操作挂网"}), 403)
    return ann, None


@bp.route("/<int:aid>/portal", methods=["GET"])
@login_required
def portal_status(aid):
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    d = portal_dict(ann)
    d["running"] = aid in _running
    d["enabled"] = portal.enabled()
    return jsonify({"ok": True, "data": d})


@bp.route("/<int:aid>/portal/publish", methods=["POST"])
@login_required
def portal_publish(aid):
    ann, err = _guard(aid)
    if err:
        return err
    if ann.status != "已确认":
        return jsonify({"ok": False, "error": "公告尚未确认发布，不能挂官网"}), 400
    if not portal.enabled():
        return jsonify({"ok": False, "error": "官网挂网功能未启用（缺 .njyy_portal.json）"}), 400
    if ann.portal_news_id:
        return jsonify({"ok": False, "error": f"已挂网（id={ann.portal_news_id}），如需重挂请先撤网"}), 400
    from flask import current_app
    started = start_publish(current_app._get_current_object(), ann,
                            session.get("display_name", ""))
    if not started:
        return jsonify({"ok": False, "error": "该公告正在挂网中，请稍候"}), 400
    return jsonify({"ok": True, "message": "已开始挂网，约需 1 分钟", "data": portal_dict(ann)})


@bp.route("/<int:aid>/portal/revoke", methods=["POST"])
@login_required
def portal_revoke(aid):
    ann, err = _guard(aid)
    if err:
        return err
    if not (ann.portal_news_id or 0):
        return jsonify({"ok": False, "error": "这条公告没有挂在官网上"}), 400
    from flask import current_app
    started = start_revoke(current_app._get_current_object(), ann,
                           session.get("display_name", ""))
    if not started:
        return jsonify({"ok": False, "error": "该公告正在处理中，请稍候"}), 400
    return jsonify({"ok": True, "message": "已开始撤网", "data": portal_dict(ann)})


@bp.route("/<int:aid>/portal/recheck", methods=["POST"])
@login_required
def portal_recheck(aid):
    """复核：直接去公网页面看一眼还在不在，顺带同步状态。"""
    ann = db.session.get(Announcement, aid)
    if not ann:
        return jsonify({"ok": False, "error": "公告不存在"}), 404
    if not ann.portal_url:
        return jsonify({"ok": False, "error": "没有挂网记录"}), 400
    ok = portal.verify(ann.portal_url)
    ann.portal_status = "已挂网" if ok else "官网上找不到"
    ann.portal_at = _now()
    db.session.commit()
    return jsonify({"ok": True, "data": portal_dict(ann), "online": ok})
