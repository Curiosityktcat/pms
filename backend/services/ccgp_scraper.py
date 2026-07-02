"""四川政府采购网 中标公告 / 合同公告 抓取（Playwright 驱动）。

数据来源接口（gpcms 开放 REST，返回 JSON）：
  站点ID  getDeploymentSiteId            -> siteId
  列表    info/selectInfoMoreChannel     -> data.rows[]   （channel 固定为「公告信息」频道）
          noticeType=00102 中标（成交）公告 / 001054 合同公告
  详情    info/getInfoById?id=<id>        -> data.content(HTML) / data.attchs[]
  原文页  /maincms-web/showNoticeContent?id=<id>

反爬要点：headless chrome 直接 goto 详情会被 ERR_EMPTY_RESPONSE 拒绝；
必须用正常 UA、先 goto 列表页建立会话，再用 page.request 调接口（带浏览器 TLS 指纹+cookie）。
抓取在 Flask 后台线程里跑 sync_playwright（线程内无 asyncio loop，可用）。
"""
import re
import datetime

BASE = "https://www.ccgp-sichuan.gov.cn"
LIST_PAGE = BASE + "/maincms-web/noticeInformation?typeId=ggxx"
NOTICE_CHANNEL = "c5bff13f-21ca-4dac-b158-cb40accd3035"   # 「公告信息」频道
REGION_CODE = "510001"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

NOTICE_TYPES = {            # 业务名 -> 网站 noticeType 码
    "中标公告": "00102",
    "合同公告": "001054",
}

# 该接口只返回「最新一页」，且 pageSize 上限 40、不支持翻页（实测）。
# 因此每次抓取拿最新 40 条/类累积入库，库里历史随抓取增长，前端分页浏览全部库存。
DEFAULT_PAGES = 1
PAGE_SIZE = 40


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _strip_html(h):
    h = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h or "", flags=re.S)
    h = re.sub(r"<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", h).strip()


def _extract_project_no(text):
    m = re.search(r"项目编号[：:\s]*([A-Za-z0-9\-（）()]{6,40})", text)
    return m.group(1).strip("（）()") if m else ""


# 表格表头/无意义词：抽到这些说明匹配偏移到了表头列，丢弃（宁缺毋滥，不抽错）
_BAD_WIN = re.compile(r"(地址|名称|金额|编号|序号|价格|数量|包号|评审|得分|排名|联系|电话|项目|无效|/|供应商|采购)")


def _extract_win_company(text, notice_type):
    # 中标人通常以「公司/中心/院/厂/部/社/店」等结尾，借此校验，避免抽到表头
    pats = [
        r"(?:中标|成交)(?:供应商|人)(?:名称)?(?:为)?[：:\s]*([一-龥（）()A-Za-z0-9]{4,40})",
        r"第一名[：:\s]*([一-龥（）()A-Za-z0-9]{4,40})",
        r"乙\s*方[（(]?(?:供应商|乙方)?[)）]?[：:\s]*([一-龥（）()A-Za-z0-9]{4,40})",
    ]
    for p in pats:
        for m in re.finditer(p, text):
            cand = m.group(1).strip("（）()")
            if _BAD_WIN.search(cand):
                continue
            if re.search(r"(公司|中心|医院|学院|大学|研究院|厂|部|社|店|事务所|集团|有限)$", cand):
                return cand
    return ""


def _extract_amount(text):
    m = re.search(r"(?:中标|成交|合同|总)(?:金额|价款)(?:[（(]?(?:人民币|元)?[)）]?)?[为：:\s]*"
                  r"(?:人民币)?\s*([0-9][0-9,]{2,}\.?\d*)\s*(万?元)?", text)
    if m:
        unit = m.group(2) or "元"
        return m.group(1) + unit
    return ""


def _launch(p):
    return p.chromium.launch(
        channel="chrome", headless=True,
        args=["--no-sandbox", "--disable-setuid-sandbox",
              "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"],
    )


def run_scrape(app, pages=DEFAULT_PAGES, fetch_detail=True):
    """抓取并 upsert 入库；返回结果消息字符串。须传 Flask app（线程内建上下文）。"""
    from playwright.sync_api import sync_playwright
    from models import db
    from models.ccgp_notice import CcgpNotice
    from models.sys_config import SysConfig

    total_new, total_upd = 0, 0
    with sync_playwright() as pw:
        browser = _launch(pw)
        try:
            ctx = browser.new_context(user_agent=UA, locale="zh-CN")
            page = ctx.new_page()
            page.goto(LIST_PAGE, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(800)

            # 动态确认 siteId（站点偶尔会变）
            try:
                sid = page.request.get(
                    f"{BASE}/gpcms/rest/web/v2/index/getDeploymentSiteId"
                    f"?domain=www.ccgp-sichuan.gov.cn&_t=1").json()["data"]["id"]
            except Exception:
                sid = "94c965cc-c55d-4f92-8469-d5875c68bd04"

            for type_name, nt in NOTICE_TYPES.items():
                url = (f"{BASE}/gpcms/rest/web/v2/info/selectInfoMoreChannel"
                       f"?siteId={sid}&channel={NOTICE_CHANNEL}&noticeType={nt}"
                       f"&currPage=1&pageSize={PAGE_SIZE}&regionCode={REGION_CODE}&_t=1")
                try:
                    rows = page.request.get(url).json().get("data", {}).get("rows", [])
                except Exception:
                    rows = []
                if rows:
                    with app.app_context():
                        for r in rows:
                            nid = r.get("id")
                            if not nid:
                                continue
                            existing = db.session.get(CcgpNotice, nid)
                            content = ""
                            project_no = win = amount = ""
                            # 详情只对新公告抓（省时间）；已有的不重复抓正文
                            if fetch_detail and not existing:
                                try:
                                    dd = page.request.get(
                                        f"{BASE}/gpcms/rest/web/v2/info/getInfoById?id={nid}"
                                    ).json().get("data", {}) or {}
                                    content = _strip_html(dd.get("content"))
                                    project_no = _extract_project_no(content)
                                    win = _extract_win_company(content, type_name)
                                    amount = _extract_amount(content)
                                except Exception:
                                    pass

                            if existing:
                                existing.title = r.get("title") or existing.title
                                existing.purchaser = r.get("purchaser") or existing.purchaser
                                existing.agency = r.get("agency") or existing.agency
                                existing.region = r.get("regionName") or existing.region
                                existing.notice_time = r.get("noticeTime") or existing.notice_time
                                existing.updated_at = _now()
                                total_upd += 1
                            else:
                                db.session.add(CcgpNotice(
                                    id=nid, notice_type=type_name,
                                    title=r.get("title") or "",
                                    project_no=project_no,
                                    purchaser=r.get("purchaser") or "",
                                    agency=r.get("agency") or "",
                                    region=r.get("regionName") or "",
                                    win_company=win, amount=amount,
                                    notice_time=r.get("noticeTime") or "",
                                    content=content,
                                    source_url=f"{BASE}/maincms-web/showNoticeContent?id={nid}",
                                    first_seen=_now(), updated_at=_now(),
                                ))
                                total_new += 1
                        db.session.commit()
                    page.wait_for_timeout(200)
        finally:
            browser.close()

    with app.app_context():
        from models.sys_config import SysConfig as _SC
        from models import db as _db
        row = _db.session.get(_SC, "ccgp_last_run")
        if row:
            row.value = _now()
        else:
            _db.session.add(_SC(key="ccgp_last_run", value=_now(), updated_at=_now()))
        _db.session.commit()

    return f"新增 {total_new} 条，更新 {total_upd} 条"
