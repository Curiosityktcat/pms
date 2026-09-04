"""代理机构服务质量考核：评分表定义 + 自动算分 + 累计分汇总。

评分表逐条抄自客户《2025年10月 版本2招标代理机构服务质量考核评价表》，
key 稳定不变（前端与历史数据都靠它对齐），标题与评分标准原文保留。

自动算分的思路——凡是 PMS 里有确切时间戳或留痕的，机器直接算出建议分，
人只需要复核；算不出来的（比如"未能充分理解采购人需求"）才留给人打。
时效类三项（编制采购文件 / 拟定合同 / 资料归档）用的是同一套阶梯：
  1 日内 +1.5，2 日内 +1，3 日内 +0.5，超 3 日每日 -0.3，超 30 日 -30

采购文件编制时效只算代理机构**实际在干活**的那几段（发出需求→第一版、
每次驳回→调整版），经办人审阅等待的时间不算在代理头上；一个项目走了
几轮就分几轮算，第一轮打分、后面的轮次只扣超期。
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
     "standard": "自采购需求发出之日起1日内拟定完毕采购文件的加1.5分；2日内加1分，3日内加0.5分；超过3日的，每日扣0.3分，超过30日的，扣30分（按第一轮计分；后续轮次超过3日的，超期部分另行累扣）"},
    {"key": "understand_need", "auto": False,
     "name": "未能充分理解采购人的需求，或未能对采购需求提出合理化的建议和意见，或未能指导采购人部门将合理的采购需求反映在采购文件中的",
     "standard": "每一次扣1-2分，每提出合理化的建议和意见，被采购人采用，每提出一条加1分。"},
    {"key": "doc_illegal", "auto": True,
     "name": "因代理机构原因，造成采购文件内容违反国家相关政策、评审办法或技术指标缺失、文件有重大偏差或失误等，导致项目时间延误、造成不良影响或带来不利后果的",
     "standard": "每一次扣1-10分"},
    {"key": "doc_messy", "auto": True,
     "name": "采购文件内容混乱，前后条款表述不一致、错误较多、评分标准表述不严谨、用词不准确，易产生错误理解，需要作出3-5处澄清修改的",
     "standard": "每一次扣1-2分（系统按驳回时记下的「代理机构文件问题」条数 + 采购文件更正次数，每处扣1.5分建议；「采购需求调整」类不计）"},
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
        "auto_hint": "系统取：第 1 轮采购需求确认 → 第 1 轮首份采购文件；后续轮次超 3 日另扣",
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


def _first_doc(pid, kind):
    """取某类附件里**第一轮**的第一份；第一轮没有就退回全项目最早的一份。

    老项目导进来时 round_number 是空的，所以不能只认 round_number==1。
    """
    rows = db.session.execute(
        db.select(ProcurementDocAttachment)
        .filter_by(project_id=pid, kind=kind)
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()
    if not rows:
        return None
    r1 = [r for r in rows if (r.round_number or 1) == 1]
    return (r1 or rows)[0]


class _Up:
    """把上传留痕包成和附件一样的形状，下面的算法不用分两种数据源。"""
    __slots__ = ("uploaded_at", "original_name")

    def __init__(self, at, name):
        self.uploaded_at, self.original_name = at, name


def _round_doc_uploads(pid, n):
    """第 n 轮代理机构交上来的采购文件，按时间先后。

    读的是上传留痕（doc_upload_events）而不是当前还活着的附件——
    代理换版本时把旧的删了，第一版的时间也不能跟着没了。
    """
    from services import doc_events
    rows = doc_events.uploads(pid, kind="doc", round_number=n)
    if rows:
        return [_Up(r.created_at, r.original_name) for r in rows]
    # 留痕还没建起来的老数据，退回读附件
    atts = db.session.execute(
        db.select(ProcurementDocAttachment)
        .filter_by(project_id=pid, kind="doc")
        .order_by(ProcurementDocAttachment.id)
    ).scalars().all()
    hit = [r for r in atts if (r.round_number or 1) == n]
    return sorted(hit, key=lambda r: (r.uploaded_at or ""))


def _doc_rejects(pid, n):
    """第 n 轮采购文件被驳回的记录，按时间先后。"""
    rows = db.session.execute(
        db.select(ApprovalLog).where(
            ApprovalLog.project_id == pid,
            ApprovalLog.node == "doc",
            ApprovalLog.action == "reject",
        ).order_by(ApprovalLog.id)
    ).scalars().all()
    hit = [r for r in rows if (r.round_number or 1) == n]
    return sorted(hit, key=lambda r: (r.created_at or ""))


def _round_segments(pid, n):
    """第 n 轮里代理机构**实际在干活**的那几段。

    黄新博 2026-09-04 定的口径：
      段一：采购人发出采购需求 → 代理做出第一版
      段二起：经办人驳回 → 代理做出调整版
    经办人审阅、等确认的时间不算在代理头上——那不是代理在拖。
    用时 = 各段天数之和。

    返回 [(说明, 起, 止, 天数)]；某段缺时间（比如驳回后再没交过东西）就不计。
    """
    segs = []
    ups = _round_doc_uploads(pid, n)
    start, _ = _round_span(pid, n)
    if start and ups:
        d = _days_between(start, ups[0].uploaded_at)
        if d is not None:
            segs.append(("发出采购需求 → 第一版采购文件",
                         _fmt_day(start), _fmt_day(ups[0].uploaded_at), d))
    for k, rj in enumerate(_doc_rejects(pid, n), start=1):
        nxt = next((u for u in ups if (u.uploaded_at or "") > (rj.created_at or "")), None)
        if not nxt:
            continue          # 驳回后没再交，这段没法算，不计（也别拿今天去凑）
        d = _days_between(rj.created_at, nxt.uploaded_at)
        if d is None:
            continue
        segs.append((f"第 {k} 次驳回 → 调整版采购文件",
                     _fmt_day(rj.created_at), _fmt_day(nxt.uploaded_at), d))
    return segs


def _fmt_day(ts):
    d = _parse(ts)
    return d.strftime("%Y-%m-%d") if d else ""


def _round_span(pid, n):
    """第 n 轮的「发出采购需求 → 交出采购文件」两个时间点。

    起点先认该轮的「采购需求确认（5.1）」——确认了代理才动手编文件，就是发出的那一刻；
    没有确认记录就退回该轮采购需求附件的上传时间。终点是该轮第一份采购文件。
    老项目导进来时 round_number 是空的，第 1 轮兜底认这些无轮次的附件。
    """
    from models.procurement_round import ProcurementRound
    rd = db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=pid, round_number=n)
    ).scalars().first()

    def _att(kind):
        rows = db.session.execute(
            db.select(ProcurementDocAttachment)
            .filter_by(project_id=pid, kind=kind)
            .order_by(ProcurementDocAttachment.id)
        ).scalars().all()
        hit = [r for r in rows if (r.round_number or 1) == n]
        return hit[0].uploaded_at if hit else None

    start = (rd.demand_confirmed_at or "").strip() if rd else ""
    if not start:
        start = _att("demand")
    return start or None, _att("doc")


def _round_numbers(pid):
    """这个项目一共走了哪几轮，从小到大。没有轮次记录就当作只有第 1 轮。"""
    from models.procurement_round import ProcurementRound
    ns = sorted({int(r.round_number or 1) for r in db.session.execute(
        db.select(ProcurementRound).filter_by(project_id=pid)).scalars().all()})
    return ns or [1]


def _overrun_only(days):
    """后续轮次的算法：只扣超期，不给加分。

    黄新博 2026-09-03 定的口径——主要考核第一次的时间，后面每一轮
    只要超过 3 日就把超期那部分扣掉，3 日内按时完成的不再重复加分
    （加分是奖励第一次就做对，返工做得快不算功劳）。
    """
    if days is None:
        return 0.0, None
    if days > 30:
        return -30.0, f"用时 {days} 日，超过 30 日"
    if days > 3:
        return round(-0.3 * (days - 3), 2), f"用时 {days} 日，超期 {days - 3} 日"
    return 0.0, f"用时 {days} 日，3 日内完成，不扣"


def _round_days(pid, n):
    """第 n 轮代理机构的总作业天数 = 各段之和；一段都算不出来就返回 (None, 说明)。"""
    segs = _round_segments(pid, n)
    if not segs:
        return None, ""
    total = sum(x[3] for x in segs)
    detail = "；".join(f"{lab} {a}→{b} {d} 日" for lab, a, b, d in segs)
    if len(segs) > 1:
        detail += f"（{' + '.join(str(x[3]) for x in segs)} = {total} 日）"
    return total, detail


def _doc_speed(pid, dates):
    """采购文件编制时效 = 第一轮的阶梯分 − 后面每一轮超过 3 日的扣分之和。

    每一轮的用时都只算代理机构实际在干活的那几段（发需求→首版、
    驳回→调整版），经办人审阅的时间不算进去。第一轮是主考核、加分
    也在这一轮拿；后面的轮次只承担超期的责任。
    """
    d1, detail1 = _round_days(pid, 1)
    if (dates or {}).get("doc_speed", {}).get("start") and \
            (dates or {}).get("doc_speed", {}).get("end"):
        # 人手填了日期就以人填的为准（系统没留痕的老项目靠这个补）
        score, basis, src, ds, de = _ladder_with_dates("doc_speed", None, None, dates)
    elif d1 is None:
        s1, e1 = _round_span(pid, 1)
        score, basis, src, ds, de = _ladder_with_dates("doc_speed", s1, e1, dates)
    else:
        score, txt = _ladder(d1)
        basis = f"{detail1}；{txt}"
        segs1 = _round_segments(pid, 1)
        src, ds, de = "auto", segs1[0][1], segs1[-1][2]

    later = []
    for n in _round_numbers(pid):
        if n <= 1:
            continue
        d, detail = _round_days(pid, n)
        if d is None:
            continue                       # 该轮没留下时间，算不了就不算，别瞎扣
        pen, txt = _overrun_only(d)
        later.append((n, pen, f"{detail}，{txt}" if detail else txt))

    hit = [x for x in later if x[1]]
    if not later:
        return score, basis, src, ds, de
    tail = "；".join(f"第 {n} 轮：{txt}{'，扣 ' + str(abs(pen)) + ' 分' if pen else ''}"
                     for n, pen, txt in later)
    if score is None:
        # 第一轮算不出来，后面轮次的扣分先摆出来，等人把第一轮日期补齐
        return (score, f"{basis}｜后续轮次：{tail}", src, ds, de)
    total = round(score + sum(p for _, p, _ in later), 2)
    if hit:
        basis = (f"第 1 轮：{basis}｜后续轮次：{tail}｜"
                 f"合计 {score:+g} {sum(p for _, p, _ in later):+g} = {total:+g} 分")
    else:
        basis = f"第 1 轮：{basis}｜后续 {len(later)} 轮均未超 3 日，不扣"
    return total, basis, src, ds, de


def auto_scores(project, dates=None):
    """算出 6 个可自动评分项的建议分。

    返回 {key: (score, basis)}；三项时效额外带日期信息，放在 LADDER_DATES 里
    （build_items 会取走塞进行里给前端画日历）。
    """
    pid = project.id
    out = {}
    ladder_dates = {}
    dates = dates or {}

    # ① 采购文件编制时效 = 第一轮阶梯分 − 后面每轮超过 3 日的扣分之和。
    #    第一轮两头都取第一轮自己的：projects.demand_confirmed_at 每轮都被覆盖、
    #    存的永远是最后一轮，拿它去配第一份采购文件就成了「起点比终点晚」
    #    （12 号项目一轮 6-02、二轮 6-15，判出来倒挂 13 天，全库 23 例都是这个原因）。
    sc, ba, src, ds, de = _doc_speed(pid, dates)
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

    # ④ 采购文件质量：驳回时逐条记下的「代理机构文件问题」+ 涉及采购文件的更正公告，
    #    每条/每次扣 1.5（考核表写的是「每一次扣1-2分」，取区间中值）。
    #    分类为「采购需求调整」的不算——那是采购人自己改了需求，代理返工不该由它背。
    from services import approval_log as alog
    doc_issues = []
    for rj in db.session.execute(
        db.select(ApprovalLog).where(
            ApprovalLog.project_id == pid,
            ApprovalLog.node == "doc",
            ApprovalLog.action == "reject",
        ).order_by(ApprovalLog.id)
    ).scalars().all():
        doc_issues += [i for i in alog.issues_of(rj)
                       if i.get("category") in alog.DEDUCT_KEYS]

    corr = db.session.execute(
        db.select(Announcement).filter_by(project_id=pid, ann_type="correction")
    ).scalars().all()
    doc_corr = [c for c in corr if "采购文件" in (c.corr_scope or "")]

    n_msg = len(doc_issues) + len(doc_corr)
    if n_msg:
        bits = []
        if doc_issues:
            bits.append(f"驳回时记下 {len(doc_issues)} 条代理机构文件问题")
        if doc_corr:
            bits.append(f"发布过 {len(doc_corr)} 次涉及采购文件的更正公告")
        detail = "；".join(f"{k + 1}. {i['text'][:40]}" for k, i in enumerate(doc_issues[:5]))
        out["doc_messy"] = (round(-1.5 * n_msg, 2),
                            f"{'、'.join(bits)}，合计 {n_msg} 处，按每处扣 1.5 分建议"
                            + (f"（{detail}）" if detail else ""))
    else:
        out["doc_messy"] = (0.0, "本项目无采购文件问题记录，也无采购文件更正")

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
