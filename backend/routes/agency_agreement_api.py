import io
import os
import tempfile
import threading
import datetime as _dt

from flask import Blueprint, request, session, jsonify, send_file, current_app
from werkzeug.utils import secure_filename

from models import db
from models.project import Project
from models.agency import Agency
from routes.utils import login_required
from services import upload_relay

bp = Blueprint("agency_agreement", __name__, url_prefix="/api/projects")

_rdweb: dict = {}
_rdweb_lock = threading.Lock()

# rd-web 审签附件（每项目一个目录：自行上传 + 从「我的模板」复制，提交时全部随单带上）
_PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ATTACH_ROOT = os.path.join(_PMS_ROOT, "uploads", "agency_agreement")
ATTACH_ALLOWED = {".docx", ".doc", ".xlsx", ".xls", ".pdf", ".jpg", ".jpeg", ".png", ".zip"}


def _attach_dir(pid: int) -> str:
    d = os.path.join(ATTACH_ROOT, str(pid))
    os.makedirs(d, exist_ok=True)
    return d


def _safe_name(name: str) -> str:
    """保留中文文件名，仅剥离路径与危险字符。"""
    name = os.path.basename(name or "").replace("\x00", "").strip()
    if name in ("", ".", ".."):
        name = secure_filename(name) or "attachment"
    return name


def _check_project_access(project):
    """经办人仅限本人项目，代理机构仅限本机构项目。返回错误响应或 None。"""
    role = session.get("role", "")
    if role == "officer" and project.officer != session.get("display_name", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    return None


@bp.route("/<int:pid>/agency-agreement", methods=["POST"])
@login_required
def generate_agency_agreement(pid):
    """按模板生成委托代理协议 Word（仅走代理项目）。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if project.is_draft:
        return jsonify({"ok": False, "error": "草稿项目无法生成代理协议"}), 400
    if not project.agency_code:
        return jsonify({"ok": False, "error": "该项目不走代理机构，无需生成代理协议"}), 400

    # 权限：经办人仅限本人项目，代理机构仅限本机构项目
    role = session.get("role", "")
    if role == "officer" and project.officer != session.get("display_name", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403

    data = request.get_json(silent=True) or {}

    # 代理机构全称
    a = db.session.execute(
        db.select(Agency).filter_by(code=project.agency_code)
    ).scalar_one_or_none()
    agency_name = (data.get("agency_name") or (a.name if a else project.agency_code)).strip()

    from services.agency_agreement_word import generate
    try:
        buf, filename = generate(
            project, agency_name,
            agency_address=(data.get("agency_address") or "").strip(),
            officer_name=(data.get("officer_name") or "").strip(),
            officer_phone=(data.get("officer_phone") or "0832-2256120").strip(),
            sign_date=(data.get("sign_date") or "").strip(),
        )
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{str(e)}"}), 500

    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=filename,
    )


# ══════════════════════════════════════════════════════════════════
# rd-web 审签附件管理（自行上传 / 从「我的模板」选用）
# ══════════════════════════════════════════════════════════════════

def _list_attachments(pid: int) -> list:
    d = _attach_dir(pid)
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


@bp.route("/<int:pid>/agency-agreement/attachments", methods=["GET"])
@login_required
def list_agency_attachments(pid):
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    err = _check_project_access(project)
    if err:
        return err
    return jsonify({"ok": True, "data": _list_attachments(pid)})


@bp.route("/<int:pid>/agency-agreement/attachments", methods=["POST"])
@login_required
def upload_agency_attachment(pid):
    """自行上传附件。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    err = _check_project_access(project)
    if err:
        return err
    f = request.files.get("file") or upload_relay.staged_file()  # 公网大文件走 OSS 中转（见 services/upload_relay.py）
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400
    name = _safe_name(f.filename)
    ext = os.path.splitext(name)[1].lower()
    if ext not in ATTACH_ALLOWED:
        return jsonify({"ok": False,
                        "error": f"不支持的附件格式：{ext or '未知'}"}), 400
    f.save(os.path.join(_attach_dir(pid), name))
    return jsonify({"ok": True, "data": _list_attachments(pid)})


@bp.route("/<int:pid>/agency-agreement/attachments/from-template", methods=["POST"])
@login_required
def add_agency_attachment_from_template(pid):
    """从「我的模板」复制一份作为附件（每个用户自己的模板库）。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    err = _check_project_access(project)
    if err:
        return err
    name = (request.get_json(silent=True) or {}).get("name", "")
    from routes.my_template_api import resolve_tpl
    src = resolve_tpl(name)
    if not src:
        return jsonify({"ok": False, "error": "模板不存在，请先在「我的模板」中上传"}), 404
    import shutil
    dst = os.path.join(_attach_dir(pid), _safe_name(os.path.basename(src)))
    shutil.copyfile(src, dst)
    return jsonify({"ok": True, "data": _list_attachments(pid)})


@bp.route("/<int:pid>/agency-agreement/attachments/<path:name>", methods=["DELETE"])
@login_required
def delete_agency_attachment(pid, name):
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    err = _check_project_access(project)
    if err:
        return err
    d = _attach_dir(pid)
    p = os.path.abspath(os.path.join(d, _safe_name(name)))
    if not p.startswith(os.path.abspath(d) + os.sep) or not os.path.isfile(p):
        return jsonify({"ok": False, "error": "附件不存在"}), 404
    os.remove(p)
    return jsonify({"ok": True, "data": _list_attachments(pid)})


# ══════════════════════════════════════════════════════════════════
# rd-web 代理协议审签直连提交
# ══════════════════════════════════════════════════════════════════

@bp.route("/<int:pid>/agency-agreement/submit-to-rdweb", methods=["POST"])
@login_required
def submit_agency_agreement_to_rdweb(pid):
    """生成委托代理协议 Word 并直接提交到 rd-web 合同审签单。"""
    project = db.session.get(Project, pid)
    if not project:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if project.is_draft:
        return jsonify({"ok": False, "error": "草稿项目不可提交"}), 400
    if not project.agency_code:
        return jsonify({"ok": False, "error": "非代理项目"}), 400

    role = session.get("role", "")
    if role == "agency" and project.agency_code != session.get("agency_code", ""):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403

    with _rdweb_lock:
        if _rdweb.get(pid, {}).get("running"):
            return jsonify({"ok": False, "error": "该项目正在提交 rd-web，请稍后重试"}), 429
        _rdweb[pid] = {"running": True, "ok": None, "serial_no": "", "msg": "提交中…"}

    from routes.utils import get_rdweb_creds
    _rdweb_user, _rdweb_pass = get_rdweb_creds(session.get("display_name", ""))

    body = request.get_json(silent=True) or {}

    # 代理机构信息
    a = db.session.execute(
        db.select(Agency).filter_by(code=project.agency_code)
    ).scalar_one_or_none()
    agency_name    = (body.get("agency_name")    or (a.name      if a else project.agency_code)).strip()
    agency_address = (body.get("agency_address") or (a.address   if a else "")).strip()
    legal_rep      = (body.get("legal_rep")      or (a.legal_rep if a else "")).strip()
    agency_phone   = (body.get("agency_phone")   or (a.phone     if a else "")).strip()
    officer_name   = (body.get("officer_name")   or project.officer or "").strip()
    officer_phone  = (body.get("officer_phone")  or "0832-2256120").strip()
    sign_date      = (body.get("sign_date")      or "").strip()
    amount_str     = (body.get("合同金额")        or "按协议约定").strip()

    rdweb_data = {
        "合同名称":       f"委托代理服务协议—{project.name}",
        "合同编码":       f"{project.number or ''}-代理-HT",
        "项目名称及包号": project.name or "",
        "归口管理科室":   project.manage_dept or "",
        "合同金额":       amount_str,
        "合同甲方":       "内江市第一人民医院",
        "甲方法定代表人": "谢晓阳",
        "甲方联系电话":   officer_phone,
        "甲方地址":       "四川省内江市市中区沱中路41号、汉安大道西段1866号",
        "合同乙方":       agency_name,
        "乙方法定代表人": legal_rep,
        "乙方联系电话":   agency_phone,
        "乙方地址":       agency_address,
        "合同类别":       "采购部合同",
        "经办人":         officer_name,
    }
    # 前端可覆盖任意字段
    overrides = body.get("data") or {}
    rdweb_data.update({k: v for k, v in overrides.items() if k in rdweb_data})

    # 提前收集需在线程中使用的项目字段（避免跨线程访问 SQLAlchemy lazy 属性）
    _proj_id     = project.id
    _proj_name   = project.name or ""
    _proj_number = project.number or ""
    app = current_app._get_current_object()

    def _worker():
        tmp_path = None
        try:
            # 应用前端对 rd-web 字段的覆盖（同步到 Word 生成参数）
            _agency_name    = rdweb_data.get("合同乙方") or agency_name
            _agency_address = rdweb_data.get("乙方地址") or agency_address
            _officer_name   = rdweb_data.get("经办人")   or officer_name
            _officer_phone  = rdweb_data.get("甲方联系电话") or officer_phone

            # 生成协议 Word 到临时文件
            from services.agency_agreement_word import generate
            buf, _ = generate(
                project, _agency_name,
                agency_address=_agency_address,
                officer_name=_officer_name,
                officer_phone=_officer_phone,
                sign_date=sign_date,
            )
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
                tf.write(buf.read())
                tmp_path = tf.name

            from services.contract_submit import submit_contract as rdweb_submit
            _display_name = f"委托代理服务协议_{rdweb_data.get('合同编码', _proj_number)}.docx"
            # 附件 = 生成的协议 Word + 项目附件目录（自行上传/模板选用）
            attachments = [{"path": tmp_path, "name": _display_name}]
            for item in _list_attachments(_proj_id):
                attachments.append({
                    "path": os.path.join(_attach_dir(_proj_id), item["name"]),
                    "name": item["name"],
                })
            res = rdweb_submit(
                data=rdweb_data,
                attachments=attachments,
                loginuser=_rdweb_user,
                password=_rdweb_pass,
            )

            # 注：代理协议独立走本模块审签，不再推送到合同管理（合同审签）。

            with _rdweb_lock:
                _rdweb[pid] = {
                    "running": False,
                    "ok":        res["ok"],
                    "serial_no": res.get("serial_no", ""),
                    "msg":       res.get("msg", ""),
                }
            # 成功且有流水号 → 落库到项目，供项目列表打标
            if res.get("ok") and res.get("serial_no"):
                try:
                    with app.app_context():
                        _p2 = db.session.get(Project, _proj_id)
                        if _p2:
                            _p2.agency_rdweb_serial_no = res.get("serial_no", "")
                            _p2.agency_rdweb_submitted_at = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            db.session.commit()
                except Exception as _pe:
                    print(f"[rdweb] 代理协议流水号落库失败 pid={_proj_id}: {_pe}", flush=True)
        except Exception as e:
            with _rdweb_lock:
                _rdweb[pid] = {"running": False, "ok": False, "serial_no": "", "msg": str(e)[:300]}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始提交 rd-web"})


@bp.route("/<int:pid>/agency-agreement/rdweb-status")
@login_required
def agency_agreement_rdweb_status(pid):
    return jsonify({"ok": True, "data": _rdweb.get(pid, {
        "running": False, "ok": None, "serial_no": "", "msg": ""
    })})
