from flask import Blueprint, request, session, jsonify
from services import bid as svc
from routes.utils import login_required

bp = Blueprint("bid", __name__, url_prefix="/api/bid")


@bp.route("", methods=["GET"])
@login_required
def list_bid():
    rows = svc.list_bid_projects(
        role=session["role"],
        agency_code=session.get("agency_code", ""),
        officer=session.get("display_name", ""),
    )
    return jsonify({"ok": True, "data": rows})


def _sess():
    return dict(
        role=session["role"],
        agency_code_session=session.get("agency_code", ""),
        officer_session=session.get("display_name", ""),
    )


def _run(fn, ok_msg, *args):
    try:
        fn(*args, **_sess())
        return jsonify({"ok": True, "message": ok_msg})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.route("/<int:pid>/can-open", methods=["POST"])
@login_required
def can_open(pid):
    """可开标：单步生效。"""
    return _run(svc.mark_can_open, "已标记为「可开标」", pid)


@bp.route("/<int:pid>/propose-fail", methods=["POST"])
@login_required
def propose_fail(pid):
    """流标第一步：代理机构提交流标 + 原因。"""
    reason = (request.get_json(force=True) or {}).get("reason", "")
    return _run(svc.propose_bid_fail, "已提交流标，待经办人确认", pid, reason)


@bp.route("/<int:pid>/confirm-fail", methods=["POST"])
@login_required
def confirm_fail(pid):
    """流标第二步：经办人确认 → 开下一轮。"""
    return _run(svc.confirm_bid_fail, "已确认流标，已自动开启下一次采购", pid)


@bp.route("/<int:pid>/revoke-fail", methods=["POST"])
@login_required
def revoke_fail(pid):
    """撤回待确认的流标。"""
    return _run(svc.revoke_bid_fail, "已撤回流标提交", pid)
