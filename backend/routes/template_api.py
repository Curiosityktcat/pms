"""模板维护：管理各功能生成 Word 所依赖的医院模板文件（查看/下载/替换）。"""
import os
import datetime
from flask import Blueprint, request, session, jsonify, send_file
from routes.utils import login_required

bp = Blueprint("template", __name__, url_prefix="/api/templates")

PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TPL_ROOT = os.path.join(PMS_ROOT, "..", "医院模板")

# 受管模板登记表：key 与各生成服务引用的路径一一对应。
TEMPLATES = [
    {"key": "auth_letter",       "label": "授权函",          "rel": ("文件汇总", "3.（打印1份盖章）内江市第一人民医院授权函.docx")},
    {"key": "agency_agreement",  "label": "委托代理协议",     "rel": ("文件汇总", "4.代理协议模板（自行采购-院内竞选项目）.docx")},
    {"key": "bid_cover",         "label": "招标文件封面",     "rel": ("1.盖章文件", "2.（打印2份盖章）招标文件封面（第xx次）.docx")},
    {"key": "result_confirm",    "label": "结果确认函",       "rel": ("1.盖章文件", "4.（打印1份盖章）结果确认函.docx")},
    {"key": "announcement",      "label": "采购公告",         "rel": ("1.盖章文件", "采购公告.docx")},
    {"key": "internal_demand",   "label": "院内竞选需求表",   "rel": ("文件汇总", "2.2院内竞选需求表.docx")},
    {"key": "procurement_demand","label": "采购需求表",       "rel": ("文件汇总", "2.2内江市第一人民医院采购需求表.docx")},
]
_BY_KEY = {t["key"]: t for t in TEMPLATES}
ALLOWED_EXT = {".docx", ".doc", ".xlsx", ".xls"}


def _abs_path(tpl):
    return os.path.abspath(os.path.join(TPL_ROOT, *tpl["rel"]))


@bp.route("", methods=["GET"])
@login_required
def list_templates():
    result = []
    for t in TEMPLATES:
        path = _abs_path(t)
        exists = os.path.isfile(path)
        info = {
            "key": t["key"],
            "label": t["label"],
            "filename": t["rel"][-1],
            "exists": exists,
            "size": os.path.getsize(path) if exists else 0,
            "updated_at": (
                datetime.datetime.fromtimestamp(os.path.getmtime(path))
                .strftime("%Y-%m-%d %H:%M") if exists else ""
            ),
        }
        result.append(info)
    return jsonify({"ok": True, "data": result})


@bp.route("/<key>/download", methods=["GET"])
@login_required
def download_template(key):
    t = _BY_KEY.get(key)
    if not t:
        return jsonify({"ok": False, "error": "未知模板"}), 404
    path = _abs_path(t)
    if not os.path.isfile(path):
        return jsonify({"ok": False, "error": "模板文件不存在"}), 404
    return send_file(path, as_attachment=True, download_name=t["rel"][-1])


@bp.route("/<key>", methods=["POST"])
@login_required
def replace_template(key):
    """替换模板文件。仅助理/负责人可操作；替换前自动备份为 .bak。"""
    from services.permission import is_admin_user
    role = session.get("role", "")
    if role not in ("assistant", "leader") and not is_admin_user(session.get("user", "")):
        return jsonify({"ok": False, "error": "权限不足"}), 403

    t = _BY_KEY.get(key)
    if not t:
        return jsonify({"ok": False, "error": "未知模板"}), 404

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "请选择文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    target_ext = os.path.splitext(t["rel"][-1])[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": "仅支持 Word/Excel 文件"}), 400
    if ext != target_ext:
        return jsonify({"ok": False, "error": f"模板要求 {target_ext} 格式"}), 400

    path = _abs_path(t)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    # 备份旧文件
    if os.path.isfile(path):
        try:
            bak = path + ".bak"
            if os.path.exists(bak):
                os.remove(bak)
            os.rename(path, bak)
        except OSError:
            pass
    f.save(path)
    return jsonify({"ok": True, "message": f"已更新模板：{t['label']}"})
