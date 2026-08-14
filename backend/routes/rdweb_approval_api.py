"""rd-web 采购项目审批流程：要件推送接口（采购文件确认函/授权函/采购结果确认函）。

两条路进来：
  ① 经办人在 PMS 确认要件时**自动推**（auto_push_on_confirm，由各确认接口调用）；
  ② 页面上「推送 rd-web 盖章」按钮**手动推/失败重推**（本文件的 POST 接口）。

自动推送有总开关 SysConfig['rdweb_auto_push']（默认开）：rd-web 里生成的是真单据，
出问题时要能一键停掉自动推、回到手工，不用改代码重启。
"""
import time

from flask import Blueprint, request, session, jsonify, current_app

from models import db
from models.project import Project
from models.sys_config import SysConfig
from routes.utils import login_required, can_view_project, get_rdweb_creds
from services import rdweb_approval_push as pusher

bp = Blueprint("rdweb_approval", __name__, url_prefix="/api/rdweb/approval")

AUTO_KEY = "rdweb_auto_push"


def auto_push_enabled() -> bool:
    row = db.session.get(SysConfig, AUTO_KEY)
    return True if row is None else (row.value or "1") not in ("0", "false", "off")


def _launch(project, kind, round_number=None, officer="", manage_dept="",
            skip_if_pushed=False):
    """统一的启动入口，返回 (ok, msg, round_number)。"""
    officer = (officer or project.officer or session.get("display_name", "")).strip()
    loginuser, password = get_rdweb_creds(session.get("display_name", ""))
    return pusher.start_push(
        current_app._get_current_object(), project, kind,
        officer=officer, loginuser=loginuser, password=password,
        round_number=round_number, manage_dept=manage_dept,
        username=session.get("user", ""),
        display_name=session.get("display_name", ""),
        skip_if_pushed=skip_if_pushed,
    )


def auto_push_on_confirm(project, kind: str, round_number=None) -> dict:
    """确认动作完成后自动推送。**绝不抛异常**——推送失败不能把确认本身带崩，
    确认已经落库了，推送失败页面上还能手动重推。"""
    try:
        if not auto_push_enabled():
            return {"auto": False, "reason": "自动推送已关闭"}
        ok, msg, rno = _launch(project, kind, round_number=round_number,
                               skip_if_pushed=True)
        return {"auto": True, "ok": ok, "msg": msg, "kind": kind, "round": rno}
    except Exception as e:      # noqa: BLE001
        return {"auto": True, "ok": False, "kind": kind, "msg": f"自动推送启动失败：{e}"[:200]}


@bp.route("/kinds")
@login_required
def kinds():
    return jsonify({"ok": True, "auto_push": auto_push_enabled(),
                    "kinds": [{"kind": k, "label": v["label"],
                               "material_type": v["material_type"]}
                              for k, v in pusher.PUSH_KINDS.items()]})


@bp.route("/auto-push", methods=["POST"])
@login_required
def set_auto_push():
    body = request.get_json(silent=True) or {}
    val = "1" if body.get("enabled", True) else "0"
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    row = db.session.get(SysConfig, AUTO_KEY)
    if row:
        row.value, row.updated_at = val, now
    else:
        db.session.add(SysConfig(key=AUTO_KEY, value=val, updated_at=now))
    db.session.commit()
    return jsonify({"ok": True, "auto_push": val == "1"})


@bp.route("/<int:pid>/status")
@login_required
def status(pid):
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_view_project(p):
        return jsonify({"ok": False, "error": "无权查看该项目"}), 403
    return jsonify({"ok": True, "auto_push": auto_push_enabled(),
                    "data": pusher.get_status(pid)})


@bp.route("/<int:pid>/<kind>", methods=["POST"])
@login_required
def push(pid, kind):
    if kind not in pusher.PUSH_KINDS:
        return jsonify({"ok": False, "error": f"未知的推送类型：{kind}"}), 400
    p = db.session.get(Project, pid)
    if not p:
        return jsonify({"ok": False, "error": "项目不存在"}), 404
    if not can_view_project(p):
        return jsonify({"ok": False, "error": "无权操作该项目"}), 403
    body = request.get_json(silent=True) or {}
    ok, msg, rno = _launch(p, kind,
                           round_number=body.get("round"),
                           officer=body.get("经办人", ""),
                           manage_dept=body.get("归口管理科室", ""))
    if not ok:
        return jsonify({"ok": False, "error": msg}), 429 if "正在推送" in msg else 400
    return jsonify({"ok": True, "msg": msg, "round": rno})
