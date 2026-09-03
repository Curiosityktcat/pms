"""代理机构服务质量考核：评分表定义 + 自动算分 + 累计分汇总。

评分表逐条抄自客户《2025年10月 版本2招标代理机构服务质量考核评价表》，
key 稳定不变（前端与历史数据都靠它对齐），标题与评分标准原文保留。

自动算分的思路——凡是 PMS 里有确切时间戳或留痕的，机器直接算出建议分，
人只需要复核；算不出来的（比如"未能充分理解采购人需求"）才留给人打。
时效类三项（编制采购文件 / 拟定合同 / 资料归档）用的是同一套阶梯：
  1 日内 +1.5，2 日内 +1，3 日内 +0.5，超 3 日每日 -0.3，超 30 日 -30
"""
import datetime
import json
import re

from models import db
from models.project import Project
from models.contract import Contract
from models.announcement import Announcement
from models.approval_log import ApprovalLog
from models.procurement_doc_attachment import ProcurementDocAttachment

# ── 15 个评分项 ────────────────────────────────────────────────────
# auto=True 表示系统能给建议分
ITEMS = [
    {"key": "doc_speed", "auto": True,
     "name": "自接到采购人发出的采购需求后，超过3日编辑完成采购文件的",
     "standard": "自采购需求发出之日起1日内拟定完毕采购文件的加1.5分；2日内加1分，3日内加0.5分；超过3日的，每日扣0.3分，超过30日的，扣30分"},
    {"key": "understand_need", "auto": False,
     "name": "未能充分理解采购人的需求，或未能对采购需求提出合理化的建议和意见，或未能指导采购人部门将合理的采购需求反映在采购文件中的",
     "standard": "每一次扣1-2分，每提出合理化的建议和意见，被采购人采用，每提出一条加1分。"},
    {"key": "doc_illegal", "auto": True,
     "name": "因代理机构原因，造成采购文件内容违反国家相关政策、评审办法或技术指标缺失、文件有重大偏差或失误等，导致项目时间延误、造成不良影响或带来不利后果的",
     "standard": "每一次扣1-10分"},
    {"key": "doc_messy", "auto": True,
     "name": "采购文件内容混乱，前后条款表述不一致、错误较多、评分标准表述不严谨、用词不准确，易产生错误理解，需要作出3-5处澄清修改的",
     "standard": "每一次扣1-2分"},
    {"key": "ann_irregular", "auto": True,
     "name": "各类公告发布不规范、不及时，或公告内容与采购文件内容不一致，导致项目时间延误、造成不良影响或带来不利后果的",
     "standard": "每一次扣1-2分"},
    {"key": "review_irregular", "auto": False,
     "name": "项目评审过程不规范，出现未统一保管评审人员通讯工具、未提醒评审专家回避情形、未要求评审人员在评审纪律认知书上签字等情形的",
     "standard": "每一次扣1-2分"},
    {"key": "no_report_violation", "auto": False,
     "name": "评审过程中发现违法违规问题未能及时向采购人或监督人员报告的",
     "standard": "每一次扣5-10分"},
    {"key": "score_inconsistent", "auto": False,
     "name": "评标委员会成员对客观评审因素评分不一致且代理机构未在复核时发现的",
     "standard": "每一次扣1-2分"},
    {"key": "contract_speed", "auto": True,
     "name": "自中标（成交）通知书发出之日起，超过3日内未按照要求协助采购人拟定合同的",
     "standard": "自中标（成交）通知书发出之日起1日内拟定合同的加1.5分；2日内加1分，3日内加0.5分；超过3日的，每日扣0.3分，超过30日的，扣30分"},
    {"key": "archive_speed", "auto": True,
     "name": "资料归档及时性：代理机构应在资料齐全的情况下3个工作日将汇编资料移交给采购人",
     "standard": "自合同签订完毕并交代理公司之日起1日内归档完毕的加1.5分；2日内加1分，3日内加0.5分；超过3日的，每日扣0.3分，超过30日的，扣30分"},
    {"key": "archive_quality", "auto": False,
     "name": "项目完成后存在归档资料不完整、汇编资料页码错乱、未按规范要求编制的",
     "standard": "每一次扣1-2分"},
    {"key": "no_answer_query", "auto": False,
     "name": "未在法定时间内对供应商的质疑作出答复的、未针对质疑内容答复的或未积极配合采购人、监管机构调查处理投诉的",
     "standard": "每一次扣5-10分"},
    {"key": "service_complaint", "auto": False,
     "name": "因服务质量、服务态度不良导致采购人采购需求部门、审计部门、供应商质疑或举报，经查属实的",
     "standard": "每一次扣1-2分"},
    {"key": "other", "auto": False,
     "name": "其他影响服务质量的行为，视情节及后果严重性予以扣分",
     "standard": "每一次扣1-2分"},
    {"key": "overall_service", "auto": False,
     "name": "服务能力及服务态度：服务过程细致耐心，服务态度良好；熟练掌握采购各项法律法规和规章制度，专业性强；对采购活动中出现的问题反应迅速，及时应对，妥善处置",
     "standard": "主观项，对项目服务整体评价，最多可加/扣2分"},
]

# ── 9 条一票否决 ──────────────────────────────────────────────────
VETO_ITEMS = [
    {"key": "v1", "name": "收受与代理项目有利害关系人的财物或其他不正当利益"},
    {"key": "v2", "name": "与采购人工作人员、供应商等串通损害采购人利益"},
    {"key": "v3", "name": "违反法律法规，向相关人员泄露项目信息或秘密的"},
    {"key": "v4", "name": "弄虚作假、干扰评标专家评标"},
    {"key": "v5", "name": "不遵守采购人管理制度、不接受采购人监督、不听取采购人合理化意见，被采购人采购部、纪检和审计等管理监督部门两次及以上书面警告"},
    {"key": "v6", "name": "在有关部门依法实施的监督检查中提供虚假情况或者拒绝有关部门依法实施监督检查的"},
    {"key": "v7", "name": "违反规定隐匿、销毁应当保存的采购文件或者伪造、变造采购文件的"},
    {"key": "v8", "name": "损害采购人利益或给采购人带来严重负面影响"},
    {"key": "v9", "name": "项目存在重大瑕疵的"},
]

SUBJ_OPTIONS = ("满意", "一般", "不满意")
# 综合评价的默认值：绝大多数项目本来就正常，默认「满意」，
# 让人只需要改那几个例外，而不是每份表都从空白逐项勾一遍。
SUBJ_DEFAULT = "满意"

# ── 三项时效的起止日期 ─────────────────────────────────────────────
# PMS 里有时间戳的直接算；没有的（最常见是归档——资料交接与备案送达都发生在
# 系统外，纸质单据上）让人在考核表里用日历补一下，补了就能算分。
# start/end 的措辞照考核表原文，人一看就知道该填哪天。
LADDER_ITEMS = {
    "doc_speed": {
        "start_label": "采购需求发出时间",
        "end_label": "采购文件拟定完成时间",
        "auto_hint": "系统取：需求确认时间 → 采购文件首次上传时间",
    },
    "contract_speed": {
        "start_label": "中标（成交）通知书发出时间",
        "end_label": "合同拟定完成时间",
        "auto_hint": "系统取：中标通知书上传时间 → 合同建单时间",
    },
    "archive_speed": {
        "start_label": "资料交接时间",
        "end_label": "备案资料送达时间",
        "auto_hint": "系统取：合同上传完成时间 → 项目归档时间",
    },
}

# ── 考核结果的处置阈值（取自考核表附注）────────────────────────────
PASS_LINE = 90          # 低于 90 分暂停下一轮项目拟派
BONUS_LINE = 10         # 多项目加分累计满 10 分，提前一轮拟派
SUSPEND_LINE = 30       # 累计加扣分达 30 分，暂停代理资格 3 个月
VALID_MONTHS = 3        # 日常考核扣分有效期 3 个月


def _parse(ts):
    """PMS 里的时间戳格式不统一（ISO / 中文 / 带空格），统一转 datetime。"""
    if not ts:
        return None
    s = str(ts).strip().replace("T", " ")
    for f in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s[:19], f)
        except ValueError:
            continue
    import re
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if m:
        return datetime.datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def _ladder(days):
    """时效阶梯：1日内+1.5 / 2日内+1 / 3日内+0.5 / 超3日每日-0.3 / 超30日-30。"""
    if days is None:
        return None, "缺少时间数据，无法自动计算"
    d = max(0, days)
    if d <= 1:
        return 1.5, f"用时 {d} 日，1 日内完成"
    if d <= 2:
        return 1.0, f"用时 {d} 日，2 日内完成"
    if d <= 3:
        return 0.5, f"用时 {d} 日，3 日内完成"
    if d > 30:
        return -30.0, f"用时 {d} 日，超过 30 日"
    over = d - 3
    return round(-0.3 * over, 2), f"用时 {d} 日，超期 {over} 日，每日扣 0.3 分"


def _days_between(a, b):
    da, dbb = _parse(a), _parse(b)
    if not da or not dbb:
        return None
    return max(0, (dbb.date() - da.date()).days)


def norm_dates(raw):
    """把前端传来的手填日期收成 {key: {"start": "YYYY-MM-DD", "end": ...}}。

    只认 LADDER_ITEMS 里的三个 key，值只留日期部分（时分秒对天数没意义），
    解析不出来的一律丢掉——宁可回落到系统自动算，也不能拿脏值去算分。
    """
    out = {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "{}")
        except Exception:
            raw = {}
    if not isinstance(raw, dict):
        return out
    for k in LADDER_ITEMS:
        v = raw.get(k) or {}
        if not isinstance(v, dict):
            continue
        one = {}
        for side in ("start", "end"):
            d = _parse(v.get(side))
            if d:
                one[side] = d.strftime("%Y-%m-%d")
        if one:
            out[k] = one
    return out


def _ladder_with_dates(key, auto_start, auto_end, dates):
    """三项时效统一入口：人填了日期就按人填的算，没填才用系统时间戳。

    人填的优先，是因为归档这类环节本来就发生在系统外（纸质交接单），
    系统时间戳只是个近似；人填的日期是台账上的真日子。
    """
    lab = LADDER_ITEMS[key]
    man = (dates or {}).get(key) or {}
    ms, me = man.get("start"), man.get("end")
    if ms and me:
        if me < ms:
            return (None, f"手填日期前后颠倒：{lab['start_label']} {ms} 晚于 {lab['end_label']} {me}，请核对",
                    "none", ms, me)
        score, basis = _ladder(_days_between(ms, me))
        return score, f"按手填日期：{ms} → {me}，{basis}", "manual", ms, me
    # 没填全就退回系统自动算，同时把系统认到的日期回给前端做日历默认值
    as_ = _parse(auto_start)
    ae_ = _parse(auto_end)
    score, basis = _ladder(_days_between(auto_start, auto_end))
    s_txt = as_.strftime("%Y-%m-%d") if as_ else (ms or "")
    e_txt = ae_.strftime("%Y-%m-%d") if ae_ else (me or "")
    # 系统时间戳倒挂（完成早于起始）不是「0 日完成」，是数据不可信——
    # _days_between 会把负数抹成 0，白送 1.5 分。这种一律退回人工填日历。
    if as_ and ae_ and ae_.date() < as_.date():
        return (None,
                f"系统时间数据异常：{lab['end_label']} {e_txt} 早于 {lab['start_label']} {s_txt}，"
                f"请用日历补填真实日期",
                "none", s_txt, e_txt)
    if score is None:
        basis = f"{basis}——请在右侧日历补填{lab['start_label']}和{lab['end_label']}"
    return score, basis, ("auto" if score is not None else "none"), s_txt, e_txt


def auto_scores(project, dates=None):
    """算出 6 个可自动评分项的建议分。

    返回 {key: (score, basis)}；三项时效额外带日期信息，放在 LADDER_DATES 里
    （build_items 会取走塞进行里给前端画日历）。
    """
    pid = project.id
    out = {}
    ladder_dates = {}
    dates = dates or {}

    # ① 采购文件编制时效：需求确认 → 采购文件首次上传
    doc_first = db.session.execute(
        db.select(ProcurementDocAttachment)
        .filter_by(project_id=pid, kind="doc")
        .order_by(ProcurementDocAttachment.id)
    ).scalars().first()
    sc, ba, src, ds, de = _ladder_with_dates(
        "doc_speed", project.demand_confirmed_at,
        doc_first.uploaded_at if doc_first else None, dates)
    out["doc_speed"] = (sc, ba)
    ladder_dates["doc_speed"] = {"start": ds, "end": de, "source": src}

    # ② 合同拟定时效：中标通知书上传 → 合同建单
    award = db.session.execute(
        db.select(ProcurementDocAttachment)
        .filter_by(project_id=pid, kind="award_notice")
        .order_by(ProcurementDocAttachment.id)
    ).scalars().first()
    contract = db.session.execute(
        db.select(Contract).filter_by(project_id=pid).order_by(Contract.id)
    ).scalars().first()
    sc, ba, src, ds, de = _ladder_with_dates(
        "contract_speed", award.uploaded_at if award else None,
        contract.created_at if contract else None, dates)
    out["contract_speed"] = (sc, ba)
    ladder_dates["contract_speed"] = {"start": ds, "end": de, "source": src}

    # ③ 归档时效：合同上传完成 → 项目归档
    signed = db.session.execute(
        db.select(Contract).filter_by(project_id=pid)
        .order_by(Contract.updated_at.desc())
    ).scalars().first()
    signed_at = signed.updated_at if signed and signed.status == "合同上传" else None
    archived_at = project.updated_at if project.status == "已归档" else None
    sc, ba, src, ds, de = _ladder_with_dates(
        "archive_speed", signed_at, archived_at, dates)
    out["archive_speed"] = (sc, ba)
    ladder_dates["archive_speed"] = {"start": ds, "end": de, "source": src}

    # ④ 采购文件澄清修改：更正公告涉及"采购文件"的次数，每次扣 1.5（区间 1-2 取中）
    corr = db.session.execute(
        db.select(Announcement).filter_by(project_id=pid, ann_type="correction")
    ).scalars().all()
    doc_corr = [c for c in corr if "采购文件" in (c.corr_scope or "")]
    if doc_corr:
        out["doc_messy"] = (round(-1.5 * len(doc_corr), 2),
                            f"发布过 {len(doc_corr)} 次涉及采购文件的更正公告，按每次扣 1.5 分建议")
    else:
        out["doc_messy"] = (0.0, "本项目无采购文件更正记录")

    # ⑤ 公告不规范：公告被驳回次数 + 涉及"采购公告"的更正次数
    # 驳回必须落在本项目自己的公告上才算数。历史上测试脚本写死过 project_id，
    # 留下一批 target_id 指向别家项目公告的假驳回（一个项目凭空多出十几次），
    # 所以这里拿 target_id 去 announcements 里对一次，对不上的不计。
    own_ann_ids = set(db.session.execute(
        db.select(Announcement.id).filter_by(project_id=pid)).scalars().all())
    reject_rows = db.session.execute(
        db.select(ApprovalLog).where(
            ApprovalLog.project_id == pid,
            ApprovalLog.node.in_(("announcement", "correction")),
            ApprovalLog.action == "reject",
        )
    ).scalars().all()
    ann_reject = sum(1 for r in reject_rows if (r.target_id or 0) in own_ann_ids)
    ann_corr = [c for c in corr if "采购公告" in (c.corr_scope or "")]
    n = int(ann_reject) + len(ann_corr)
    if n:
        out["ann_irregular"] = (round(-1.5 * n, 2),
                                f"公告被驳回 {ann_reject} 次、采购公告更正 {len(ann_corr)} 次，"
                                f"合计 {n} 次，按每次扣 1.5 分建议")
    else:
        out["ann_irregular"] = (0.0, "公告一次通过，无驳回与更正")

    # ⑥ 采购文件质量（违规/重大偏差）：采购文件被驳回次数做提示，分值仍由人定
    own_doc_ids = set(db.session.execute(
        db.select(ProcurementDocAttachment.id).filter_by(project_id=pid)).scalars().all())
    doc_reject_rows = db.session.execute(
        db.select(ApprovalLog).where(
            ApprovalLog.project_id == pid,
            ApprovalLog.node == "doc",
            ApprovalLog.action == "reject",
        )
    ).scalars().all()
    # 同上：target_id 对不上本项目采购文件的不计
    doc_reject = sum(1 for r in doc_reject_rows
                     if (r.target_id or 0) in own_doc_ids or not r.target_id)
    # 这一项分值必须由人定（"重大偏差"的严重程度机器判断不了），
    # 但驳回次数是客观事实，摆出来供打分参考，所以建议分恒为 0、只给依据。
    out["doc_illegal"] = (0.0,
                          f"提示：采购文件被驳回 {doc_reject} 次，请核对驳回原因后据实扣分"
                          if doc_reject else "采购文件未被驳回过")

    out["LADDER_DATES"] = ladder_dates
    return out


def build_items(project, saved=None, dates=None):
    """出一份完整评分项列表：带自动建议分、人工填的分、三项时效的起止日期。"""
    auto = auto_scores(project, dates)
    ladder_dates = auto.pop("LADDER_DATES", {})
    saved_map = {}
    if saved:
        for it in saved:
            saved_map[it.get("key")] = it
    out = []
    for spec in ITEMS:
        k = spec["key"]
        a = auto.get(k)
        row = dict(spec)
        row["auto_score"] = a[0] if a else None
        row["auto_basis"] = a[1] if a else ""
        s = saved_map.get(k)
        if s and s.get("score") is not None:
            row["score"] = s.get("score")
            row["note"] = s.get("note", "")
        else:
            # 没人工填过就先用建议分（人可改）
            row["score"] = a[0] if a and a[0] is not None else 0
            row["note"] = ""
        if k in LADDER_ITEMS:
            d = ladder_dates.get(k, {})
            row["date_start"] = d.get("start", "")
            row["date_end"] = d.get("end", "")
            row["date_source"] = d.get("source", "none")
            row["start_label"] = LADDER_ITEMS[k]["start_label"]
            row["end_label"] = LADDER_ITEMS[k]["end_label"]
            row["auto_hint"] = LADDER_ITEMS[k]["auto_hint"]
        out.append(row)
    return out


def total_of(items):
    return round(100.0 + sum(float(i.get("score") or 0) for i in items), 2)


def month_range(start, end):
    """把「2026-01」「2026-06」这样的起止月份换成半开区间 [起, 止)。

    传空就是不限，两头都能单独给。止月是**含**当月的，所以上界取下个月 1 号。
    """
    lo = hi = None
    m = re.match(r"^(\d{4})-?(\d{1,2})$", (start or "").strip())
    if m:
        lo = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-01T00:00:00"
    m = re.match(r"^(\d{4})-?(\d{1,2})$", (end or "").strip())
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        y, mo = (y + 1, 1) if mo >= 12 else (y, mo + 1)
        hi = f"{y:04d}-{mo:02d}-01T00:00:00"
    return lo, hi


def agency_summary(agency_code, months=VALID_MONTHS, start=None, end=None):
    """某代理机构的考核汇总，给出处置建议（对应考核表附注 1-5 条）。

    默认看「近 N 个月」（考核办法里扣分的有效期）；
    传了 start/end 就改看指定月份区间——统计「2026 年以来」「1 到 6 月」这类口径要用它。
    """
    from models.agency_assessment import AgencyAssessment
    lo, hi = month_range(start, end)
    ranged = bool(lo or hi)
    conds = [AgencyAssessment.agency_code == agency_code,
             AgencyAssessment.status == "已提交"]
    if ranged:
        if lo:
            conds.append(AgencyAssessment.assessed_at >= lo)
        if hi:
            conds.append(AgencyAssessment.assessed_at < hi)
        period = f"{(lo or '')[:7] or '最早'} 至 {(end or '').strip() or '最新'}"
    else:
        cutoff = (datetime.datetime.now()
                  - datetime.timedelta(days=months * 30)).isoformat(timespec="seconds")
        conds.append(AgencyAssessment.assessed_at >= cutoff)
        period = f"近 {months} 个月"
    rows = db.session.execute(db.select(AgencyAssessment).where(*conds)).scalars().all()
    if not rows:
        return {"agency_code": agency_code, "count": 0, "avg": None, "net": 0.0,
                "veto": 0, "below_count": 0, "flags": [], "period": period,
                "advice": f"{period}无已提交的考核记录"}

    net = round(sum((r.total_score or 100) - 100 for r in rows), 2)   # 加扣分净额
    avg = round(sum(r.total_score or 100 for r in rows) / len(rows), 2)
    veto = sum(1 for r in rows if r.veto_hit)
    below = [r for r in rows if (r.total_score or 100) < PASS_LINE]

    flags, advice = [], []
    if veto:
        flags.append("一票否决")
        advice.append(f"有 {veto} 个项目触发一票否决 —— 按考核办法暂停代理资格一年")
    if net <= -SUSPEND_LINE:
        flags.append("累计扣分达30")
        advice.append(f"{period}累计扣分 {abs(net)} 分（达 {SUSPEND_LINE} 分）—— 暂停代理资格 3 个月")
    if net >= BONUS_LINE:
        flags.append("累计加分达10")
        advice.append(f"{period}累计加分 {net} 分（达 {BONUS_LINE} 分）—— 可提前一轮拟派项目")
    if below:
        flags.append("有低于90分的项目")
        advice.append(f"{len(below)} 个项目得分低于 {PASS_LINE} 分 —— 暂停下一轮项目拟派")
    if not advice:
        advice.append("考核正常，无处置建议")

    return {
        "agency_code": agency_code, "count": len(rows), "avg": avg, "net": net,
        "veto": veto, "below_count": len(below), "flags": flags,
        "advice": "；".join(advice), "months": months, "period": period,
    }


def dump_items(items):
    """只存人填的部分，自动建议分每次实时重算（数据变了建议也跟着变）。"""
    return json.dumps(
        [{"key": i["key"], "score": i.get("score"), "note": i.get("note", "")} for i in items],
        ensure_ascii=False)
