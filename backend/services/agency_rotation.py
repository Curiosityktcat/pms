"""代理机构轮派。

规则（见项目分发需求）：
- 院内竞选 / 院内单一来源采购 → 在「参与轮次」的代理机构里按 rotation_seq 顺序轮派下一家；
- 政府采购 → 若判定为「内江市政府采购中心」项目（集采/医疗设备）则指派政采中心（不占轮次），
  否则同样走 7 家顺序轮派；
- 紧急采购等不走代理 → 返回 None。

轮派指针存在 SysConfig（key=agency_rotation_pointer，值=上次指派的代理 id）。
顺序由采购部助理维护（调整 rotation_seq / 启停 active）。
"""
import datetime

from models import db
from models.agency import Agency
from models.sys_config import SysConfig

POINTER_KEY = "agency_rotation_pointer"
_ROTATION_METHODS = ("院内竞选", "院内单一来源采购")


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def rotation_agencies():
    """参与轮次且启用的代理机构，按 rotation_seq、id 升序。"""
    return db.session.execute(
        db.select(Agency)
        .filter_by(in_rotation=1, active=1)
        .order_by(Agency.rotation_seq, Agency.id)
    ).scalars().all()


def central_agency():
    """内江市政府采购中心（不参与轮次的启用代理，取第一条）。"""
    return db.session.execute(
        db.select(Agency)
        .filter_by(in_rotation=0, active=1)
        .order_by(Agency.id)
    ).scalars().first()


def next_rotation_agency(advance=True):
    """返回轮次里的下一家；advance=True 时推进指针。无可轮派代理则 None。"""
    rota = rotation_agencies()
    if not rota:
        return None
    row = db.session.get(SysConfig, POINTER_KEY)
    last_id = int(row.value) if row and (row.value or "").isdigit() else None
    idx = next((i for i, a in enumerate(rota) if a.id == last_id), -1)
    nxt = rota[(idx + 1) % len(rota)]
    if advance:
        if row is None:
            db.session.add(SysConfig(key=POINTER_KEY, value=str(nxt.id), updated_at=_now()))
        else:
            row.value = str(nxt.id)
            row.updated_at = _now()
        db.session.commit()
    return nxt


def assign_agency(method, is_central=False, advance=True):
    """按规则返回应指派的 Agency（不落库，调用方决定写到哪）。

    method 不走代理（如紧急采购）→ None。
    """
    m = method or ""
    if m in _ROTATION_METHODS:
        return next_rotation_agency(advance=advance)
    if m == "政府采购":
        return central_agency() if is_central else next_rotation_agency(advance=advance)
    return None
