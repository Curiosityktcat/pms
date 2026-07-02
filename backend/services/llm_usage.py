"""大模型 token 用量记录与统计（按账号）。须在 Flask app 上下文内调用。"""
import datetime

from models import db
from models.llm_usage import LlmUsage


def record(username, display_name, feature, model, usage, agency_code=""):
    """写一条用量记录。usage 为模型返回的 usage dict；
    传入 agency_code 时，按 token 从该代理机构余额扣费。
    记录失败静默回滚，绝不影响主流程。"""
    try:
        if not usage:
            return
        total = int(usage.get("total_tokens") or 0)
        row = LlmUsage(
            username=username or "",
            display_name=display_name or "",
            feature=feature or "",
            model=model or "",
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=total,
            created_at=datetime.datetime.now().isoformat(timespec="seconds"),
        )
        db.session.add(row)
        db.session.commit()
        # 代理机构按量扣费（内部账号不扣）
        if agency_code:
            from services.billing import charge
            charge(agency_code, total)
    except Exception:
        db.session.rollback()


def summary():
    """按账号聚合：调用次数、各项 token 合计、最近使用时间。按总量降序。"""
    rows = db.session.execute(
        db.select(
            LlmUsage.username,
            db.func.max(LlmUsage.display_name),
            db.func.count(LlmUsage.id),
            db.func.sum(LlmUsage.prompt_tokens),
            db.func.sum(LlmUsage.completion_tokens),
            db.func.sum(LlmUsage.total_tokens),
            db.func.max(LlmUsage.created_at),
        )
        .group_by(LlmUsage.username)
        .order_by(db.func.sum(LlmUsage.total_tokens).desc())
    ).all()
    return [{
        "username": r[0] or "",
        "display_name": r[1] or "",
        "calls": r[2] or 0,
        "prompt_tokens": int(r[3] or 0),
        "completion_tokens": int(r[4] or 0),
        "total_tokens": int(r[5] or 0),
        "last_used": r[6] or "",
    } for r in rows]


def recent(limit=100):
    """最近的调用明细（默认 100 条）。"""
    rows = db.session.execute(
        db.select(LlmUsage).order_by(LlmUsage.id.desc()).limit(limit)
    ).scalars().all()
    return [r.to_dict() for r in rows]
