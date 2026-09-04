"""采购文件上传留痕的统一入口。

只增不改：上传记一条，删除再记一条，原来那条 upload 不动。
考核算编制时效读的是这里，所以代理机构换了版本、删了文件，
「第一版是几号交的」都还在。
"""
import datetime

from flask import session

from models import db
from models.doc_upload_event import DocUploadEvent
from models.procurement_doc_attachment import ProcurementDocAttachment


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _who(key):
    """取当前操作人。没有请求上下文时返回空串——AI 生成采购文件是在后台
    线程里跑的（只有 app_context，没有 session），直接读 session 会当场抛错。
    """
    try:
        return session.get(key, "") or ""
    except Exception:
        return ""


def record(att, action="upload", *, when=None, operator_name=None):
    """记一条上传/删除留痕。att 是 ProcurementDocAttachment（删除时也还在内存里）。

    不 commit —— 跟调用方在同一个事务里提交，避免出现「文件删了留痕没记上」。
    """
    row = DocUploadEvent(
        project_id=att.project_id,
        round_number=att.round_number or 1,
        kind=att.kind or "",
        action=action,
        attachment_id=att.id,
        original_name=(att.original_name or "")[:300],
        file_size=att.file_size or 0,
        sha256=att.sha256 or "",
        operator=_who("user"),
        operator_name=(operator_name if operator_name is not None
                       else (_who("display_name") or _who("user"))),
        operator_role=_who("role"),
        created_at=when or _now(),
    )
    db.session.add(row)
    return row


def uploads(project_id, kind=None, round_number=None):
    """某项目的上传留痕（只要 upload，按时间先后）。删掉的版本也在里面。"""
    conds = [DocUploadEvent.project_id == project_id,
             DocUploadEvent.action == "upload"]
    if kind:
        conds.append(DocUploadEvent.kind == kind)
    rows = db.session.execute(
        db.select(DocUploadEvent).where(*conds).order_by(DocUploadEvent.id)
    ).scalars().all()
    if round_number is not None:
        rows = [r for r in rows if (r.round_number or 1) == round_number]
    return sorted(rows, key=lambda r: (r.created_at or ""))


def timeline(project_id, kind=None):
    """完整时间线：上传 + 删除都要，给页面显示「谁在几号交了什么、又删了什么」。"""
    conds = [DocUploadEvent.project_id == project_id]
    if kind:
        conds.append(DocUploadEvent.kind == kind)
    rows = db.session.execute(
        db.select(DocUploadEvent).where(*conds).order_by(DocUploadEvent.id)
    ).scalars().all()
    alive = {a.id for a in db.session.execute(
        db.select(ProcurementDocAttachment).filter_by(project_id=project_id)).scalars().all()}
    out = []
    for r in rows:
        d = r.to_dict()
        d["alive"] = r.action == "upload" and r.attachment_id in alive
        out.append(d)
    return out


def backfill():
    """给还没有留痕的历史附件补一条 upload 事件（按它自己的 uploaded_at）。

    只补缺的，跑多少遍都一样。补不回已经被删掉的那些——那些记录连同文件
    一起没了，只能靠考核表里的日历手工填。
    """
    have = {r[0] for r in db.session.execute(
        db.select(DocUploadEvent.attachment_id).where(
            DocUploadEvent.action == "upload",
            DocUploadEvent.attachment_id.isnot(None)))}
    n = 0
    for att in db.session.execute(
            db.select(ProcurementDocAttachment)).scalars().all():
        if att.id in have:
            continue
        db.session.add(DocUploadEvent(
            project_id=att.project_id, round_number=att.round_number or 1,
            kind=att.kind or "", action="upload", attachment_id=att.id,
            original_name=(att.original_name or "")[:300],
            file_size=att.file_size or 0, sha256=att.sha256 or "",
            operator="", operator_name=att.uploaded_by or "", operator_role="",
            created_at=att.uploaded_at or ""))
        n += 1
    if n:
        db.session.commit()
    return n
