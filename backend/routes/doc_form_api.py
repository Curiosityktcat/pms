# -*- coding: utf-8 -*-
"""文档式表单 API —— /api/doc-forms

学四川政采的「文档式填空编辑」：模板(章节/字段)由 services/doc_templates.py 配置，
数据结构化存 doc_forms.data(JSON)，导出按模板生成 Word。
"""
import json
import datetime

from flask import Blueprint, request, session, jsonify, send_file

from models import db
from models.doc_form import DocForm
from models.project import Project
from routes.utils import login_required, can_view_project
from services import doc_templates as T

bp = Blueprint("doc_form", __name__, url_prefix="/api/doc-forms")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _proj_ok(project_id):
    """按项目归属校验（officer 本人 / agency 本机构 / 助理·负责人·管理员全部）。"""
    return can_view_project(db.session.get(Project, project_id))


@bp.route("/template/<key>", methods=["GET"])
@login_required
def get_template(key):
    tpl = T.get_template(key)
    if not tpl:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    return jsonify({"ok": True, "data": tpl})


@bp.route("/status/<key>", methods=["GET"])
@login_required
def status_map(key):
    """该模板下各项目的填写状态(供列表页标注)。"""
    rows = db.session.execute(
        db.select(DocForm).filter_by(template_key=key)
    ).scalars().all()
    out = {}
    for r in rows:
        if not _proj_ok(r.project_id):   # 隔离：只标注本人可见项目的状态
            continue
        try:
            data = json.loads(r.data or "{}")
        except Exception:
            data = {}
        out[r.project_id] = {"status": r.status, **T.progress(key, data),
                             "updated_at": r.updated_at}
    return jsonify({"ok": True, "data": out})


def _get_or_create(project_id, key):
    row = db.session.execute(
        db.select(DocForm).filter_by(project_id=project_id, template_key=key)
    ).scalar_one_or_none()
    if row:
        return row, False
    proj = db.session.get(Project, project_id)
    data = T.prefill_from_project(key, proj)
    now = _now()
    row = DocForm(project_id=project_id, template_key=key,
                  data=json.dumps(data, ensure_ascii=False),
                  status="草稿", created_at=now, updated_at=now,
                  updated_by=session.get("display_name", ""))
    db.session.add(row)
    db.session.commit()
    return row, True


@bp.route("/<int:project_id>/<key>", methods=["GET"])
@login_required
def get_form(project_id, key):
    if not T.get_template(key):
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not _proj_ok(project_id):
        return jsonify({"ok": False, "error": "无权访问该项目表单"}), 403
    row, _ = _get_or_create(project_id, key)
    d = row.to_dict()
    proj = db.session.get(Project, project_id)
    d["project_name"] = proj.name if proj else ""
    d["project_number"] = (proj.number or "") if proj else ""
    d["progress"] = T.progress(key, d["data"])
    return jsonify({"ok": True, "data": d})


@bp.route("/<int:project_id>/<key>", methods=["PUT"])
@login_required
def save_form(project_id, key):
    if not T.get_template(key):
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not _proj_ok(project_id):
        return jsonify({"ok": False, "error": "无权修改该项目表单"}), 403
    row, _ = _get_or_create(project_id, key)
    body = request.get_json(force=True) or {}
    if "data" in body and isinstance(body["data"], dict):
        row.data = json.dumps(body["data"], ensure_ascii=False)
    if "status" in body and body["status"] in ("草稿", "已完成"):
        row.status = body["status"]
    row.updated_at = _now()
    row.updated_by = session.get("display_name", "")
    db.session.commit()
    d = row.to_dict()
    d["progress"] = T.progress(key, d["data"])
    return jsonify({"ok": True, "data": d})


@bp.route("/<int:project_id>/<key>/word", methods=["GET"])
@login_required
def export_word(project_id, key):
    if not T.get_template(key):
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    if not _proj_ok(project_id):
        return jsonify({"ok": False, "error": "无权访问该项目表单"}), 403
    row, _ = _get_or_create(project_id, key)
    data = row.to_dict()["data"]
    buf = T.generate_word(key, data)
    proj = db.session.get(Project, project_id)
    tpl = T.get_template(key)
    fname = f"{tpl['name']}_{(proj.name if proj else project_id)}.docx".replace("/", "-")
    return send_file(
        buf, as_attachment=True, download_name=fname,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
