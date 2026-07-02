from flask import Blueprint, request, jsonify
from routes.utils import admin_required
from services import llm_usage, billing

bp = Blueprint("llm_usage", __name__, url_prefix="/api/llm-usage")


@bp.route("/summary", methods=["GET"])
@admin_required
def get_summary():
    """按账号汇总 token 用量（仅管理员）。"""
    price = billing.get_price()
    rows = llm_usage.summary()
    for r in rows:  # 附带费用（元）
        r["cost"] = round(billing.cost_of(r["total_tokens"], price), 4)
    return jsonify({"ok": True, "data": rows, "price_per_million": price})


@bp.route("/billing", methods=["GET"])
@admin_required
def get_billing():
    """计费设置 + 各代理机构余额（仅管理员）。"""
    return jsonify({"ok": True, "data": {
        "price_per_million": billing.get_price(),
        "init_balance": billing.DEFAULT_INIT_BALANCE,
        "balances": billing.list_balances(),
    }})


@bp.route("/price", methods=["PUT"])
@admin_required
def update_price():
    """设置每百万 token 价格（元）。"""
    data = request.get_json(silent=True) or {}
    try:
        price = float(data.get("price"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "价格无效"}), 400
    return jsonify({"ok": True, "data": {"price_per_million": billing.set_price(price)}})


@bp.route("/balance", methods=["PUT"])
@admin_required
def update_balance():
    """设置某代理机构余额（元）。"""
    data = request.get_json(silent=True) or {}
    code = (data.get("agency_code") or "").strip()
    if not code:
        return jsonify({"ok": False, "error": "缺少代理机构"}), 400
    try:
        balance = float(data.get("balance"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "余额无效"}), 400
    return jsonify({"ok": True, "data": {"balance": billing.set_balance(code, balance)}})


@bp.route("/recent", methods=["GET"])
@admin_required
def get_recent():
    """最近的调用明细（仅管理员）。"""
    limit = min(500, max(1, int(request.args.get("limit", 100))))
    return jsonify({"ok": True, "data": llm_usage.recent(limit)})
