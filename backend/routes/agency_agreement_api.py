import io
import os
import tempfile
import threading
import datetime as _dt

from flask import Blueprint, request, session, jsonify, send_file, current_app
from models import db
from models.project import Project
from models.agency import Agency
from models.contract import Contract
from routes.utils import login_required

bp = Blueprint("agency_agreement", __name__, url_prefix="/api/projects")

_rdweb: dict = {}
_rdweb_lock = threading.Lock()


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

    app = current_app._get_current_object()
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
            res = rdweb_submit(
                data=rdweb_data,
                attachments=[{"path": tmp_path, "name": _display_name}],
                loginuser=_rdweb_user,
                password=_rdweb_pass,
            )

            # rd-web 成功后自动在 PMS 创建代理协议合同记录（已审核状态）
            if res.get("ok"):
                _ensure_agency_contract(
                    app=app,
                    project_id=_proj_id,
                    project_name=_proj_name,
                    project_number=_proj_number,
                    agency_name=_agency_name,
                    legal_rep=legal_rep,
                    agency_phone=agency_phone,
                    agency_address=_agency_address,
                    amount_str=amount_str,
                    officer_name=_officer_name,
                )

            with _rdweb_lock:
                _rdweb[pid] = {
                    "running": False,
                    "ok":        res["ok"],
                    "serial_no": res.get("serial_no", ""),
                    "msg":       res.get("msg", ""),
                }
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


def _ensure_agency_contract(*, app, project_id, project_name, project_number,
                             agency_name, legal_rep, agency_phone, agency_address,
                             amount_str, officer_name):
    """在 PMS 合同表中创建代理协议合同记录（幂等：相同 contract_number 只创建一次）。"""
    contract_number = f"{project_number}-代理-HT"
    contract_name   = f"委托代理服务协议—{project_name}"
    now = _dt.datetime.now().isoformat(timespec="seconds")

    with app.app_context():
        existing = db.session.execute(
            db.select(Contract).filter_by(
                project_id=project_id, contract_number=contract_number
            )
        ).scalar_one_or_none()
        if existing:
            return  # 已存在，幂等

        c = Contract(
            project_id      = project_id,
            contract_name   = contract_name,
            contract_number = contract_number,
            package_no      = "代理",
            status          = "审核完成",   # rd-web 提交即视为已审核
            supplier_name      = agency_name,
            supplier_legal_rep = legal_rep,
            supplier_contact   = agency_phone,
            supplier_address   = agency_address,
            amount_is_text  = 1,
            amount_text     = amount_str or "按协议约定",
            created_by      = officer_name,
            created_at      = now,
            updated_at      = now,
        )
        db.session.add(c)
        db.session.commit()
