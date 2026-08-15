"""授权的读时生效判定与权限汇总。"""
import json
from datetime import date

from models import db
from models.authorization import Authorization
from models.dept import Dept


STATE_ACTIVE = "生效"


def parse_perm_keys(value):
    """把库中的 JSON 权限数组收口成字符串列表，坏数据按空权限处理。"""
    try:
        keys = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return [key for key in keys if isinstance(key, str)] if isinstance(keys, list) else []


def effective_state(auth, dept_head_now, today=None):
    """返回授权当前状态；每次读取都判定，负责人变更后无需等待任务同步。"""
    if auth.status != "active":
        return "已撤销"
    current = (today or date.today()).isoformat()
    if current < auth.valid_from:
        return "未开始"
    if current > auth.valid_to:
        return "已过期"
    if auth.source == "delegate" and (dept_head_now or "") != (auth.granter_head_snapshot or ""):
        return "授权人已换人"
    return STATE_ACTIVE


def effective_permissions(username):
    """汇总某账号收到的全部生效授权，不改变岗位基础权限表。"""
    rows = db.session.execute(
        db.select(Authorization).filter_by(grantee_username=username, status="active")
    ).scalars().all()
    if not rows:
        return []
    dept_codes = {row.granter_dept_code for row in rows if row.source == "delegate"}
    heads = dict(db.session.execute(
        db.select(Dept.code, Dept.head_name).where(Dept.code.in_(dept_codes))
    ).all()) if dept_codes else {}
    out = []
    seen = set()
    for row in rows:
        if effective_state(row, heads.get(row.granter_dept_code, "")) != STATE_ACTIVE:
            continue
        for key in parse_perm_keys(row.perm_keys):
            if key not in seen:
                seen.add(key)
                out.append(key)
    return out

