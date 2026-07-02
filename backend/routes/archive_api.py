"""项目归档：汇总项目要件并归档/撤销归档。"""
import datetime
import os
import tempfile
import threading
from flask import Blueprint, session, jsonify, send_file, current_app
from models import db
from models.project import Project
from models.auth_letter_record import AuthLetterRecord
from models.contract import Contract
from models.procurement_result import ProcurementResult
from routes.utils import login_required, can_view_project

_rdweb: dict = {}
_rdweb_lock = threading.Lock()

bp = Blueprint("archive", __name__, url_prefix="/api/archive")

ARCHIVED = "已归档"
# 撤销归档后回退到的状态
REVOKE_STATUS = "合同签订"


def _count_map(model):
    """一次分组统计 {project_id: 件数}，避免逐项目 N 次 COUNT 查询。"""
    rows = db.session.execute(
        db.select(model.project_id, db.func.count()).group_by(model.project_id)
    ).all()
    return {pid: cnt for pid, cnt in rows}


@bp.route("", methods=["GET"])
@login_required
def list_archive():
    """列出可归档/已归档项目及其要件统计。"""
    role = session.get("role", "")
    officer = session.get("display_name", "")
    agency_code = session.get("agency_code", "")

    rows = db.session.execute(
        db.select(Project)
        .filter(Project.is_draft == 0, Project.is_deleted == 0)
        .order_by(Project.id.desc())
    ).scalars().all()

    # 三类要件件数各一次分组查询（原先每项目 3 次 COUNT，N+1 → 常数）
    auth_map = _count_map(AuthLetterRecord)
    contract_map = _count_map(Contract)
    result_map = _count_map(ProcurementResult)

    result = []
    for p in rows:
        if role == "officer" and p.officer != officer:
            continue
        if role == "agency" and p.agency_code != agency_code:
            continue
        result.append({
            "id": p.id,
            "number": p.number or "",
            "name": p.name or "",
            "officer": p.officer or "",
            "manage_dept": p.manage_dept or "",
            "agency_code": p.agency_code or "",
            "status": p.status or "",
            "archived": p.status == ARCHIVED,
            "auth_letter_count": auth_map.get(p.id, 0),
            "contract_count": contract_map.get(p.id, 0),
            "result_count": result_map.get(p.id, 0),
        })
    return jsonify({"ok": True, "data": result})


@bp.route("/<int:pid>/print-bundle", methods=["GET"])
@login_required
def print_bundle(pid):
    """一键打印资料：按轮次顺序合并采购文件确认函/封面(×2)/授权函/采购结果确认函为单个 docx。"""
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_view_project(p):
        return jsonify({"ok": False, "error": "无权查看该项目"}), 403
    from services.archive_print import build_print_bundle
    try:
        buf, manifest = build_print_bundle(p)
    except Exception as e:
        return jsonify({"ok": False, "error": f"生成失败：{e}"}), 500
    if buf is None:
        return jsonify({"ok": False, "error": "该项目暂无可打印的归档要件"}), 400
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=False,
        download_name=f"{p.number or p.name}-归档资料.docx",
    )


def _can_archive():
    role = session.get("role", "")
    from services.permission import is_admin_user
    return role in ("assistant", "pd_assistant", "leader") or is_admin_user(session.get("user", ""))


@bp.route("/<int:pid>", methods=["POST"])
@login_required
def archive_project(pid):
    """归档项目（仅助理/负责人/管理员）。"""
    if not _can_archive():
        return jsonify({"ok": False, "error": "仅采购部助理/负责人可归档"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if p.is_draft:
        return jsonify({"ok": False, "error": "草稿项目不可归档"}), 400
    p.status = ARCHIVED
    p.updated_at = datetime.datetime.now().isoformat(timespec="seconds")
    db.session.commit()
    return jsonify({"ok": True, "message": "已归档", "status": p.status})


@bp.route("/<int:pid>/revoke", methods=["POST"])
@login_required
def revoke_archive(pid):
    """撤销归档，状态回退到「合同签订」。"""
    if not _can_archive():
        return jsonify({"ok": False, "error": "仅采购部助理/负责人可操作"}), 403
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if p.status != ARCHIVED:
        return jsonify({"ok": False, "error": "该项目未归档"}), 400
    p.status = REVOKE_STATUS
    p.updated_at = datetime.datetime.now().isoformat(timespec="seconds")
    db.session.commit()
    return jsonify({"ok": True, "message": "已撤销归档", "status": p.status})


# ── rd-web 采购项目审批直连提交 ────────────────────────────────────────────

@bp.route("/<int:pid>/submit-to-rdweb", methods=["POST"])
@login_required
def submit_approval_to_rdweb(pid):
    """生成归档资料包并直接提交到 rd-web 采购项目审批流程。"""
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_view_project(p):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403

    with _rdweb_lock:
        if _rdweb.get(pid, {}).get("running"):
            return jsonify({"ok": False, "error": "该项目正在提交 rd-web，请稍后重试"}), 429
        _rdweb[pid] = {"running": True, "ok": None, "serial_no": "", "msg": "提交中…"}

    from routes.utils import get_rdweb_creds
    _rdweb_user, _rdweb_pass = get_rdweb_creds(session.get("display_name", ""))

    app = current_app._get_current_object()

    from flask import request as _req
    body = _req.get_json(silent=True) or {}
    project_name_text = body.get("项目名称") or "采购文件确认函，授权函，采购结果确认函"
    material_type     = body.get("项目资料名称") or "备案资料"
    manage_dept       = body.get("归口管理科室") or p.manage_dept or ""
    officer           = body.get("经办人") or "曾旌城"

    # 预存提交所需的项目数据（避免跨线程 SQLAlchemy lazy-load）
    _pid      = p.id
    _pnumber  = p.number or ""
    _pname    = p.name or ""

    def _worker():
        tmp_path = None
        try:
            # 生成归档资料包 Word 到临时文件
            with app.app_context():
                _p = db.session.get(Project, _pid)
                from services.archive_print import build_print_bundle
                buf, _ = build_print_bundle(_p)

            if buf:
                with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tf:
                    tf.write(buf.read())
                    tmp_path = tf.name
                display_name = f"{_pnumber or _pname}-归档资料.docx"
                attachments = [{"path": tmp_path, "name": display_name}]
            else:
                attachments = []

            from services.procurement_approval_submit import submit_approval
            res = submit_approval(
                manage_dept=manage_dept,
                project_name_text=project_name_text,
                material_type=material_type,
                officer=officer,
                attachments=attachments,
                loginuser=_rdweb_user,
                password=_rdweb_pass,
            )
            with _rdweb_lock:
                _rdweb[_pid] = {
                    "running": False,
                    "ok":        res["ok"],
                    "serial_no": res.get("serial_no", ""),
                    "msg":       res.get("msg", ""),
                }
        except Exception as e:
            with _rdweb_lock:
                _rdweb[_pid] = {"running": False, "ok": False, "serial_no": "", "msg": str(e)[:300]}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"ok": True, "msg": "已开始提交 rd-web"})


@bp.route("/<int:pid>/rdweb-status")
@login_required
def archive_rdweb_status(pid):
    return jsonify({"ok": True, "data": _rdweb.get(pid, {
        "running": False, "ok": None, "serial_no": "", "msg": ""
    })})
