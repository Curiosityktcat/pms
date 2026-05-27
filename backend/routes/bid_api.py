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


@bp.route("/<int:pid>/mark", methods=["POST"])
@login_required
def mark(pid):
    data = request.get_json(force=True) or {}
    value = data.get("value", "")
    try:
        svc.mark_bid(
            pid, value,
            role=session["role"],
            agency_code_session=session.get("agency_code", ""),
            officer_session=session.get("display_name", ""),
        )
        return jsonify({"ok": True, "message": f"已标记为「{value}」"})
    except PermissionError as e:
        return jsonify({"ok": False, "error": str(e)}), 403
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
