"""项目进展引擎：以采购轮次系统为唯一真相，逐轮逐节点聚合状态/时间/操作人。

同一套聚合服务两处：
  ① 项目流程页点开项目时的「分轮时间线图」（build_progress 完整输出）；
  ② 各阶段列表的统一筛选——current_round / current_stage 决定项目此刻该在哪个阶段。

务必只读轮次系统（ProcurementRound/Package/各节点表），不要读 projects 上的
demand_confirmed/doc_confirmed/can_open 镜像位——那些开下一轮即被清零，画不出跨轮历史。
"""
import json

from models import db
from models.procurement_round import ProcurementRound
from models.procurement_doc_attachment import ProcurementDocAttachment
from models.announcement import Announcement
from models.procurement_result import ProcurementResult
from models.package import Package
from models.contract import Contract
from models.inquiry_letter import InquiryLetter
from models.inquiry_review import InquiryReview

# 走代理招标（含公告/开标/评审）的采购方式——完整节点集
AGENCY_TRACK_METHODS = ("院内竞选", "院内单一来源采购")

NODE_LABELS = {
    "demand_confirm": "采购需求确认",
    "doc_upload":     "代理机构上传文件",
    "doc_confirm":    "采购文件确认",
    "announce":       "采购公告发布",
    "bid_open":       "开标标记",
    "result":         "采购结果确认",
    "contract":       "合同签订",
}
AGENCY_NODES = ["demand_confirm", "doc_upload", "doc_confirm",
                "announce", "bid_open", "result", "contract"]
# 非代理轨道（其它精简流程）的节点集
SIMPLE_NODES = ["demand_confirm", "doc_confirm", "result", "contract"]

# 询/议价、紧急采购轨道：不走采购需求/文件确认，直接 发函→评审→合同→归档。
# 状态以 询/议价函(inquiry_letters) + 评审(inquiry_reviews) 为真相，不读 ProcurementRound。
INQUIRY_TRACK_METHODS = ("院内询价", "院内议价", "医用耗材紧急采购")
INQUIRY_NODES = ["inquiry", "review", "contract"]
NODE_LABELS["inquiry"] = "询/议价函"
NODE_LABELS["review"] = "项目评审"


def _node(key, done, at="", by="", **extra):
    d = {"key": key, "label": NODE_LABELS[key],
         "done": bool(done), "at": at or "", "by": by or ""}
    d.update(extra)
    return d


def build_progress(project):
    """返回 {"project": {...}, "rounds": [{round_number, status, nodes:[...]}, ...]}。"""
    pid = project.id
    method = project.method or ""
    if method in INQUIRY_TRACK_METHODS:
        return _build_inquiry_progress(project)
    node_keys = AGENCY_NODES if method in AGENCY_TRACK_METHODS else SIMPLE_NODES

    rounds = db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=pid)
        .order_by(ProcurementRound.round_number.asc())
    ).scalars().all()

    atts = db.session.execute(
        db.select(ProcurementDocAttachment).filter_by(project_id=pid)
        .order_by(ProcurementDocAttachment.uploaded_at.asc())
    ).scalars().all()
    anns = db.session.execute(
        db.select(Announcement).filter_by(project_id=pid, ann_type="procurement")
    ).scalars().all()
    results = db.session.execute(
        db.select(ProcurementResult).filter_by(project_id=pid)
    ).scalars().all()
    packages = db.session.execute(
        db.select(Package).filter_by(project_id=pid)
    ).scalars().all()
    contracts = db.session.execute(
        db.select(Contract).filter_by(project_id=pid)
    ).scalars().all()
    contract_by_pkg = {}
    for c in contracts:
        contract_by_pkg.setdefault(str(c.package_no), c)

    def doc_files(rn):
        return [{"name": a.original_name or "", "at": a.uploaded_at or "", "by": a.uploaded_by or ""}
                for a in atts if (a.round_number or 1) == rn and (a.kind or "") == "doc"]

    def ann_for(rn):
        cand = [a for a in anns if (a.round_number or 1) == rn]
        confirmed = [a for a in cand if a.status == "已确认"]
        return (confirmed or cand or [None])[0]

    def result_for(rn):
        cand = [r for r in results if (r.round_number or 1) == rn and r.status == "已确认"]
        return (cand or [None])[0]

    out_rounds = []
    for rnd in rounds:
        rn = rnd.round_number or 1
        nodes = []
        for key in node_keys:
            if key == "demand_confirm":
                nodes.append(_node(key, rnd.demand_confirmed,
                                   rnd.demand_confirmed_at, rnd.demand_confirmed_by))
            elif key == "doc_upload":
                files = doc_files(rn)
                first = files[0] if files else {}
                nodes.append(_node(key, bool(files),
                                   first.get("at", ""), first.get("by", ""), files=files))
            elif key == "doc_confirm":
                nodes.append(_node(key, rnd.doc_confirmed,
                                   rnd.doc_confirmed_at, rnd.doc_confirmed_by))
            elif key == "announce":
                a = ann_for(rn)
                nodes.append(_node(key, bool(a and a.status == "已确认"),
                                   a.confirmed_at if a else "", a.confirmed_by if a else "",
                                   ann_status=(a.status if a else "")))
            elif key == "bid_open":
                confirmed = rnd.can_open_status == "已确认"
                nodes.append(_node(key, confirmed,
                                   rnd.can_open_confirmed_at or rnd.can_open_at,
                                   rnd.can_open_confirmed_by or rnd.can_open_by,
                                   result_value=(rnd.can_open or ""),
                                   open_status=(rnd.can_open_status or ""),
                                   reason=(rnd.can_open_reason or "")))
            elif key == "result":
                r = result_for(rn)
                pkgs = []
                if r:
                    try:
                        pkgs = json.loads(r.packages_json or "[]")
                    except Exception:
                        pkgs = []
                nodes.append(_node(key, bool(r),
                                   r.updated_at if r else "", r.created_by if r else "",
                                   packages=pkgs))
            elif key == "contract":
                won = [p for p in packages if (p.won_round or 0) == rn]
                items, done_all = [], bool(won)
                for p in won:
                    c = contract_by_pkg.get(str(p.package_no))
                    signed = bool(c and c.status == "合同上传")
                    if not signed:
                        done_all = False
                    items.append({
                        "package_no": p.package_no, "winner": p.winner or "",
                        "signed": signed,
                        "at": (c.sign_date or c.updated_at) if c else "",
                        "contract_no": c.contract_number if c else "",
                    })
                nodes.append(_node(key, done_all, packages=items))
        out_rounds.append({"round_number": rn, "status": rnd.status or "", "nodes": nodes})

    current_round, current_stage = _derive_current(out_rounds)
    return {
        "project": {
            "id": pid, "name": project.name, "number": project.number or "",
            "method": method, "current_round": current_round, "current_stage": current_stage,
        },
        "rounds": out_rounds,
    }


def _derive_current(out_rounds):
    """当前轮 = 最新轮；current_stage = 最新轮里第一个未完成节点的 key。

    特例：本轮开标标记为「流标」→ 该轮终止、待开下一轮，current_stage='round_failed'；
    本轮全部节点完成 → current_stage='done'。
    """
    if not out_rounds:
        return 0, ""
    latest = out_rounds[-1]
    by_key = {n["key"]: n for n in latest["nodes"]}
    bid = by_key.get("bid_open")
    if bid and bid["done"] and bid.get("result_value") == "流标":
        return latest["round_number"], "round_failed"
    for n in latest["nodes"]:
        if not n["done"]:
            return latest["round_number"], n["key"]
    return latest["round_number"], "done"


def _build_inquiry_progress(project):
    """询/议价、紧急采购轨道的进展：每封询/议价函 = 一轮，节点 发函→评审→(中选则)合同。

    数据真相 = inquiry_letters(发函/状态) + inquiry_reviews(评审/中选废标) + contracts(签约)，
    不读 ProcurementRound 的需求/文件确认位（这几个方式本就不做这两步）。
    """
    pid = project.id
    letters = db.session.execute(
        db.select(InquiryLetter).filter_by(project_id=pid).order_by(InquiryLetter.id)
    ).scalars().all()
    reviews = {r.inquiry_id: r for r in db.session.execute(
        db.select(InquiryReview).filter_by(project_id=pid)
    ).scalars().all()}
    signed = next((c for c in db.session.execute(
        db.select(Contract).filter_by(project_id=pid)
    ).scalars().all() if c.status == "合同上传"), None)

    out_rounds = []
    for idx, letter in enumerate(letters, 1):
        rv = reviews.get(letter.id)
        nodes = [_node("inquiry", letter.status in ("进行中", "已完成"),
                       letter.updated_at or letter.created_at, letter.created_by)]
        rv_done = bool(rv and rv.status == "已完成")
        nodes.append(_node("review", rv_done,
                           rv.completed_at if rv else "", rv.completed_by if rv else "",
                           result_value=(rv.result_type if rv else "")))
        # 合同节点仅出现在「中选」轮（废标轮已废、待开下一轮）
        if rv_done and rv.result_type == "中选":
            nodes.append(_node("contract", bool(signed),
                               (signed.sign_date or signed.updated_at) if signed else "", "",
                               packages=([{"package_no": signed.package_no, "signed": True,
                                           "contract_no": signed.contract_number}] if signed else [])))
        rstatus = "已废标" if (rv_done and rv.result_type == "废标") else (letter.status or "进行中")
        out_rounds.append({"round_number": idx, "status": rstatus, "nodes": nodes})

    cr, cs = _derive_current_inquiry(out_rounds)
    return {
        "project": {
            "id": pid, "name": project.name, "number": project.number or "",
            "method": project.method or "", "current_round": cr, "current_stage": cs,
        },
        "rounds": out_rounds,
    }


def _derive_current_inquiry(out_rounds):
    """询/议价轨道当前阶段：最新轮第一个未完成节点；评审废标→round_failed；全完成→done。"""
    if not out_rounds:
        return 0, ""
    latest = out_rounds[-1]
    rv = next((n for n in latest["nodes"] if n["key"] == "review"), None)
    if rv and rv["done"] and rv.get("result_value") == "废标":
        return latest["round_number"], "round_failed"
    for n in latest["nodes"]:
        if not n["done"]:
            return latest["round_number"], n["key"]
    return latest["round_number"], "done"


def _inquiry_stage_map(inquiry_ids):
    """批量版（供 stage_map）：返回 {pid: {current_round,current_stage,pending_contract}}。"""
    from types import SimpleNamespace as _NS
    letters_by = {}
    for row in db.session.execute(
        db.select(InquiryLetter.project_id, InquiryLetter.id, InquiryLetter.status)
        .where(InquiryLetter.project_id.in_(inquiry_ids))
        .order_by(InquiryLetter.id)
    ).all():
        letters_by.setdefault(row.project_id, []).append(
            _NS(id=row.id, status=row.status))
    reviews_by_inq = {row.inquiry_id: _NS(status=row.status, result_type=row.result_type)
                      for row in db.session.execute(
        db.select(InquiryReview.inquiry_id, InquiryReview.status, InquiryReview.result_type)
        .where(InquiryReview.project_id.in_(inquiry_ids))
    ).all()}
    signed_pids = {r.project_id for r in db.session.execute(
        db.select(Contract.project_id).where(
            Contract.project_id.in_(inquiry_ids), Contract.status == "合同上传")
    ).all()}

    out = {}
    for pid in inquiry_ids:
        letters = letters_by.get(pid, [])
        if not letters:
            out[pid] = {"current_round": 0, "current_stage": "", "pending_contract": 0}
            continue
        latest = letters[-1]
        rv = reviews_by_inq.get(latest.id)
        rn = len(letters)
        if not (rv and rv.status == "已完成"):
            stage = "inquiry" if latest.status == "待办" else "review"
        elif rv.result_type == "废标":
            stage = "round_failed"
        elif pid not in signed_pids:
            stage = "contract"
        else:
            stage = "done"
        out[pid] = {"current_round": rn, "current_stage": stage, "pending_contract": 0}
    return out


def _stage_for(p, rnd, rn, ann_ok, res_ok):
    """单项目当前轮的阶段判定（轻量，供列表批量派生用）。

    与 build_progress 的节点完成判定一致；doc_upload 不单独成阶段（并入 5.2 文件确认）。
    """
    agency = (p.method or "") in AGENCY_TRACK_METHODS
    if not rnd.demand_confirmed:
        return "demand_confirm"
    if not rnd.doc_confirmed:
        return "doc_confirm"
    if agency:
        if (p.id, rn) not in ann_ok:
            return "announce"
        if rnd.can_open_status != "已确认":
            return "bid_open"
        if rnd.can_open == "流标":
            return "round_failed"   # 正常会自动开下一轮，仅兜底遗留数据
    if (p.id, rn) not in res_ok:
        return "result"
    return "done"


def stage_map(project_ids):
    """批量返回 {project_id: {"current_round", "current_stage", "pending_contract"}}。

    一次性载入轮次/公告/结果/包/合同，内存里按项目算阶段，避免逐项目 N+1。
    pending_contract = 已中标但未签订（合同未上传）的包数，供合同阶段筛选。
    """
    ids = list(project_ids)
    if not ids:
        return {}
    from models.project import Project

    # 只取用得上的列：_stage_for 只看 p.id / p.method，不需要整个 Project 实体
    from types import SimpleNamespace as _NS
    projects = {row.id: _NS(id=row.id, method=row.method) for row in db.session.execute(
        db.select(Project.id, Project.method).where(Project.id.in_(ids))
    ).all()}

    latest = {}
    for row in db.session.execute(
        db.select(ProcurementRound.project_id, ProcurementRound.round_number,
                  ProcurementRound.demand_confirmed, ProcurementRound.doc_confirmed,
                  ProcurementRound.can_open_status, ProcurementRound.can_open)
        .where(ProcurementRound.project_id.in_(ids))
        .order_by(ProcurementRound.round_number.asc())
    ).all():
        latest[row.project_id] = _NS(                  # 升序，最终留最大轮
            project_id=row.project_id, round_number=row.round_number,
            demand_confirmed=row.demand_confirmed, doc_confirmed=row.doc_confirmed,
            can_open_status=row.can_open_status, can_open=row.can_open)

    # 状态过滤下推到 SQL：原来是全量拉出来再在 Python 里 if
    ann_ok = {(r.project_id, r.round_number or 1) for r in db.session.execute(
        db.select(Announcement.project_id, Announcement.round_number).where(
            Announcement.project_id.in_(ids),
            Announcement.ann_type == "procurement",
            Announcement.status == "已确认")
    ).all()}

    res_ok = {(r.project_id, r.round_number or 1) for r in db.session.execute(
        db.select(ProcurementResult.project_id, ProcurementResult.round_number).where(
            ProcurementResult.project_id.in_(ids),
            ProcurementResult.status == "已确认")
    ).all()}

    signed = {(r.project_id, str(r.package_no)) for r in db.session.execute(
        db.select(Contract.project_id, Contract.package_no).where(
            Contract.project_id.in_(ids), Contract.status == "合同上传")
    ).all()}

    pending = {}
    for row in db.session.execute(
        db.select(Package.project_id, Package.package_no).where(
            Package.project_id.in_(ids), Package.status == "已中标")
    ).all():
        if (row.project_id, str(row.package_no)) not in signed:
            pending[row.project_id] = pending.get(row.project_id, 0) + 1

    # 询/议价、紧急采购方式单独按 函件/评审 派生（不读 ProcurementRound）
    inquiry_ids = [pid for pid in ids
                   if projects.get(pid) and (projects[pid].method or "") in INQUIRY_TRACK_METHODS]
    inquiry_out = _inquiry_stage_map(inquiry_ids) if inquiry_ids else {}

    out = {}
    for pid in ids:
        if pid in inquiry_out:
            out[pid] = inquiry_out[pid]
            continue
        p = projects.get(pid)
        rnd = latest.get(pid)
        if not p or not rnd:
            out[pid] = {"current_round": 0, "current_stage": "", "pending_contract": pending.get(pid, 0)}
            continue
        rn = rnd.round_number or 1
        out[pid] = {
            "current_round": rn,
            "current_stage": _stage_for(p, rnd, rn, ann_ok, res_ok),
            "pending_contract": pending.get(pid, 0),
        }
    return out
