"""我的模板库（按用户隔离）。

每个登录用户可上传自己的模板文件，在代理协议 rd-web 审签附件等处
从自己的模板库中选用。存储：uploads/my_templates/<username>/。
"""
import datetime as _dt
import os

from flask import Blueprint, request, session, jsonify, send_file
from werkzeug.utils import secure_filename

from routes.utils import login_required

bp = Blueprint("my_template", __name__, url_prefix="/api/my-templates")

_PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MY_TPL_ROOT = os.path.join(_PMS_ROOT, "uploads", "my_templates")
TPL_ALLOWED = {".docx", ".doc", ".xlsx", ".xls", ".pdf",
               ".jpg", ".jpeg", ".png", ".zip"}


def _safe_name(name: str) -> str:
    """保留中文文件名，仅剥离路径与危险字符。"""
    name = os.path.basename(name or "").replace("\x00", "").strip()
    if name in ("", ".", ".."):
        name = secure_filename(name) or "template"
    return name


def user_tpl_dir() -> str:
    """当前登录用户的模板目录（不存在则创建）。"""
    owner = _safe_name(session.get("user", "")) or "_anonymous"
    d = os.path.join(MY_TPL_ROOT, owner)
    os.makedirs(d, exist_ok=True)
    return d


def resolve_tpl(name: str) -> str | None:
    """当前用户模板名 → 绝对路径；不存在/越界返回 None。"""
    d = user_tpl_dir()
    p = os.path.abspath(os.path.join(d, _safe_name(name)))
    if not p.startswith(os.path.abspath(d) + os.sep) or not os.path.isfile(p):
        return None
    return p


def _list() -> list:
    d = user_tpl_dir()
    out = []
    for n in sorted(os.listdir(d)):
        p = os.path.join(d, n)
        if os.path.isfile(p):
            out.append({
                "name": n,
                "size": os.path.getsize(p),
                "updated_at": _dt.datetime.fromtimestamp(os.path.getmtime(p))
                .strftime("%Y-%m-%d %H:%M"),
            })
    return out


@bp.route("", methods=["GET"])
@login_required
def list_my_templates():
    return jsonify({"ok": True, "data": _list()})


@bp.route("", methods=["POST"])
@login_required
def upload_my_template():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    name = _safe_name(f.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in TPL_ALLOWED:
        return jsonify({"ok": False,
                        "error": f"不支持的模板格式：{ext or '未知'}"}), 400
    f.save(os.path.join(user_tpl_dir(), name))
    return jsonify({"ok": True, "data": _list()})


@bp.route("/<path:name>", methods=["DELETE"])
@login_required
def delete_my_template(name):
    p = resolve_tpl(name)
    if not p:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    os.remove(p)
    return jsonify({"ok": True, "data": _list()})


@bp.route("/<path:name>/download", methods=["GET"])
@login_required
def download_my_template(name):
    p = resolve_tpl(name)
    if not p:
        return jsonify({"ok": False, "error": "模板不存在"}), 404
    return send_file(p, as_attachment=True,
                     download_name=os.path.basename(p))
