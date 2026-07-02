"""AI token 计费与代理机构余额。须在 Flask app 上下文内调用。

计价：每百万 token 收费 price 元（默认 10 元/百万 token）。
余额：每个代理机构一个 AgencyBalance(agency_code, balance)，初始 100 元。
"""
import datetime

from models import db
from models.sys_config import SysConfig
from models.agency import Agency
from models.agency_balance import AgencyBalance

CFG_PRICE = "llm_price_per_million"   # 每百万 token 价格（元）
DEFAULT_PRICE = 10.0
DEFAULT_INIT_BALANCE = 100.0          # 代理机构初始余额（元）


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def get_price():
    """每百万 token 价格（元）。"""
    row = db.session.get(SysConfig, CFG_PRICE)
    try:
        return float(row.value) if row and row.value else DEFAULT_PRICE
    except (TypeError, ValueError):
        return DEFAULT_PRICE


def set_price(price):
    price = max(0.0, float(price))
    row = db.session.get(SysConfig, CFG_PRICE)
    if row:
        row.value = str(price)
        row.updated_at = _now()
    else:
        db.session.add(SysConfig(key=CFG_PRICE, value=str(price), updated_at=_now()))
    db.session.commit()
    return price


def cost_of(tokens, price=None):
    """按 token 数算费用（元）。"""
    p = get_price() if price is None else price
    return (int(tokens or 0) / 1_000_000.0) * p


def seed_balances(init=DEFAULT_INIT_BALANCE):
    """为尚无余额记录的代理机构播种初始余额（启动时调用，幂等）。"""
    agencies = db.session.execute(db.select(Agency)).scalars().all()
    existing = {b.agency_code for b in
                db.session.execute(db.select(AgencyBalance)).scalars().all()}
    added = 0
    for a in agencies:
        if a.code and a.code not in existing:
            db.session.add(AgencyBalance(agency_code=a.code, balance=init,
                                         updated_at=_now()))
            added += 1
    if added:
        db.session.commit()
    return added


def get_balance(agency_code):
    if not agency_code:
        return None
    row = db.session.get(AgencyBalance, agency_code)
    return row.balance if row else None


def _ensure_row(agency_code):
    row = db.session.get(AgencyBalance, agency_code)
    if row is None:
        row = AgencyBalance(agency_code=agency_code, balance=0, updated_at=_now())
        db.session.add(row)
    return row


def set_balance(agency_code, balance):
    """直接设置余额（管理员改值）。"""
    row = _ensure_row(agency_code)
    row.balance = round(float(balance), 4)
    row.updated_at = _now()
    db.session.commit()
    return row.balance


def adjust_balance(agency_code, delta):
    """增减余额（充值 delta>0 / 扣费 delta<0），返回新余额。"""
    row = _ensure_row(agency_code)
    row.balance = round((row.balance or 0) + float(delta), 4)
    row.updated_at = _now()
    db.session.commit()
    return row.balance


def charge(agency_code, tokens):
    """按 token 扣费，返回扣减的费用（元）。无 agency_code 则不扣。"""
    if not agency_code or not tokens:
        return 0.0
    c = cost_of(tokens)
    if c > 0:
        adjust_balance(agency_code, -c)
    return c


def list_balances():
    """列出各代理机构余额（带名称），按余额升序（少的在前，便于关注）。"""
    agencies = {a.code: a.name for a in
                db.session.execute(db.select(Agency)).scalars().all()}
    rows = db.session.execute(db.select(AgencyBalance)).scalars().all()
    out = [{
        "agency_code": r.agency_code,
        "agency_name": agencies.get(r.agency_code, r.agency_code),
        "balance": round(r.balance or 0, 4),
        "updated_at": r.updated_at or "",
    } for r in rows]
    out.sort(key=lambda x: x["balance"])
    return out
