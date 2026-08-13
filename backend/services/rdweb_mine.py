# -*- coding: utf-8 -*-
"""抓取「分发给我(黄新博)的采购需求审签表·待处理」→ 项目池。

**2026-08-03 重写要点（修「串页」+ 漏抓）：**
  ① **字段一律取自列表表格本身**（rd-web 待处理列表的表头就带全部字段：归口管理科室/
     需求科室/项目名称/预算金额/限价金额/项目基本情况/采购组织形式/采购方式/项目编号/
     项目所属分类），不再靠「点开详情→流程打印→pdftotext」拿字段。
     旧做法一旦详情面板没刷新（rd-web 只有 **一个** `#appUpgradeDetail` 面板复用），
     就会把上一条的 PDF 当成本条解析 → 项目名/科室张冠李戴（实测 7 条被写成别的项目名）。
  ② 详情面板只用来**下载附件 + 存审签表 PDF**，且全部定位**限定在 `#appUpgradeDetail` 内**，
     打开后先用列表里的项目名**校验面板确实换成了本条**，不匹配就重试/放弃本条附件
     （字段照写，不会因此丢数据），绝不拿别人的附件往本条上挂。
  ③ 审签表 PDF 生成后再 pdftotext 复核项目名，对不上就丢弃不入库。
  ④ 分页逐页遍历（`ul.pagination li.page a`），翻页后校验首条流水号确实变了。
只读 + 下载，绝不点接收/驳回/盖章。
"""
import os
import re
import subprocess
import tempfile
import threading
import time

from models import db
from models.project_distribution import (
    ProjectDistribution, ProjectDistributionAttachment, RdwebAccount)
from services.rdweb_scraper import map_method, _parse_amount, _now, _attach_dir

MY_OWNER = "黄新博"
MY_NODE = "采购部项目经办人"
SOURCE_TAG = "rd-经办人抓取"
WF_NAME = "采购需求审签表"
APP_MARK = "appUpgrade/app/65f2acb"
LOGIN_URL = "https://rd-web.mobimedical.cn/"
PANEL = "#appUpgradeDetail"          # rd-web 详情面板（全局唯一、各条复用 → 必须逐条校验）
MAX_ITEMS = 60
MAX_PAGES = 20
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")

_lock = threading.Lock()
_state = {"running": False, "last_msg": "", "last_run": 0}


def status():
    return dict(_state)


def _creds():
    row = db.session.execute(
        db.select(RdwebAccount).filter_by(owner=MY_OWNER)).scalar_one_or_none()
    if not row or not (row.phone and row.password):
        raise RuntimeError(f"未找到 {MY_OWNER} 的 rd-web 账号（rdweb_accounts）")
    return row.phone, row.password


def _state_path(loginuser):
    return os.path.expanduser(f"~/pms/.rdweb_session_{re.sub(r'[^\\w]', '_', loginuser)}.json")


# ── 列表表格 → 结构化行（字段的唯一真源）────────────────────────────────
_ROWS_JS = r"""
() => {
  const clean = s => (s || '').replace(/\s+/g, ' ').trim();
  // 表头：取到第一个「操作」为止（页面里表头会重复出现两套：固定头 + 表体）
  const ths = [...document.querySelectorAll('th')].map(t => clean(t.innerText));
  const head = [];
  for (const t of ths) { head.push(t); if (t === '操作') break; }
  const rows = [...document.querySelectorAll('tr')]
    .map(tr => [...tr.querySelectorAll('td,th')].map(td => clean(td.innerText)))
    .filter(cs => cs.some(c => /^20\d{11}$/.test(c)));
  return rows.map(cs => {
    const o = {};
    head.forEach((h, i) => { if (h) o[h] = cs[i] || ''; });
    const sn = cs.find(c => /^20\d{11}$/.test(c)) || '';
    // 列错位保护：表头位上的流水号对不上就标记为「未对齐」，调用方降级处理
    o._aligned = (o['流水号'] === sn) && !!clean(o['项目名称'] || '');
    o['流水号'] = sn;
    return o;
  });
}
"""

_PANEL_JS = ("()=>{const e=document.querySelector('%s');"
             "return (e && e.getClientRects().length) ? e.innerText : '';}" % PANEL)


def _panel_text(fr):
    try:
        return fr.evaluate(_PANEL_JS) or ""
    except Exception:
        return ""


def _close_panel(pg, fr, tries=5):
    """关掉详情面板并**确认已关**。面板全局唯一，残留会让下一条点开时读到旧内容。"""
    for _ in range(tries):
        if not _panel_text(fr):
            return True
        try:
            fr.evaluate("""()=>{
              const p=document.querySelector('%s'); if(!p) return;
              const btn=[...p.querySelectorAll('a,button,i,span,div')].find(e=>{
                const t=(e.innerText||'').trim();
                return t==='×' || t==='关闭' || /close/i.test(String(e.className));
              });
              if(btn) btn.click();
            }""" % PANEL)
        except Exception:
            pass
        try:
            pg.keyboard.press("Escape")
        except Exception:
            pass
        pg.wait_for_timeout(700)
    return not _panel_text(fr)


def _open_detail(pg, fr, serial, expect_name, tries=3):
    """点开某条详情并**校验面板确实是本条**（用列表里的项目名比对）。
    返回面板文本；校验不过返回 ""（调用方放弃本条附件，但字段照写）。"""
    key = _name_key(expect_name)
    for _ in range(tries):
        _close_panel(pg, fr)
        try:
            fr.locator(f"text={serial}").first.click(timeout=8000)
        except Exception:
            pg.wait_for_timeout(1200)
            continue
        for _ in range(24):                       # 最多等 12s 渲染
            txt = _panel_text(fr)
            if txt and key and key in txt:
                return txt
            pg.wait_for_timeout(500)
    return ""


def _download_item(pg, fr, serial, expect_name, tmp):
    """面板内下载全部附件 + 存审签表 PDF。定位全部限定在 PANEL 内。"""
    files, pdf_path = [], None
    if not _open_detail(pg, fr, serial, expect_name):
        _close_panel(pg, fr)
        return [], None, "详情面板未切换到本条（已跳过附件，字段取自列表）"
    dl = fr.locator(f"{PANEL} a.downLoad")
    n = dl.count()
    for i in range(n):
        try:
            with pg.expect_download(timeout=25000) as di:
                dl.nth(i).click()
            dd = di.value
            p = os.path.join(tmp, f"{serial}_{i}_{dd.suggested_filename}")
            dd.save_as(p)
            files.append((dd.suggested_filename, p))
        except Exception:
            pass
    try:
        with pg.context.expect_page(timeout=15000) as pinfo:
            fr.locator(f"{PANEL} button:has-text('流程打印')").first.click(timeout=8000)
        np = pinfo.value
        np.wait_for_load_state("networkidle", timeout=20000)
        np.wait_for_timeout(1500)
        cand = os.path.join(tmp, f"{serial}_审签表.pdf")
        np.pdf(path=cand, format="A4", print_background=True,
               margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"})
        np.close()
        pdf_path = cand if _pdf_matches(cand, expect_name) else None
    except Exception:
        pdf_path = None
    _close_panel(pg, fr)
    pg.wait_for_timeout(600)
    return files, pdf_path, ""


# ── 审签表 PDF 解析（列表里被截断的长字段用它补全）──────────────────────
def _field(text, label, stops):
    m = re.search(re.escape(label) + r"(.*?)(" +
                  "|".join(re.escape(s) for s in stops) + r")", text, re.S)
    return re.sub(r"[ \t\r\n]+", "", m.group(1)).strip() if m else ""


def _parse_pdf_fields(pdf_path):
    """从审签表 PDF 取全文字段。注意：**项目编号一律不从这里取**——PDF 里该字段常为空，
    紧随其后的是附件文件名，正则会把文件名当编号（历史脏数据 25QNMP080/xxx.xlsx 就是这么来的）。"""
    t = _pdf_text(pdf_path)
    if not t:
        return {}
    return {
        "项目名称": _field(t, "项目名称", ["预算金额", "限价金额", "项目基本情况"]),
        "项目基本情况": _field(t, "项目基本情况", ["采购组织形式", "采购方式"]),
        "采购组织形式": _field(t, "采购组织形式", ["采购方式", "项目编号"]),
        "采购方式": _field(t, "采购方式", ["项目编号", "采购需求", "项目所属分类"]),
        "项目所属分类": _field(t, "项目所属分类", ["开始", "归口管理科室经办人", "价格"]),
        "归口管理科室": _field(t, "归口管理科室", ["需求科室"]),
        "需求科室": _field(t, "需求科室", ["项目名称"]),
        "预算金额": _field(t, "预算金额", ["限价金额"]),
        "限价金额": _field(t, "限价金额", ["项目基本情况"]),
    }


def _truncated(v):
    """列表单元格对长文本会截断成「…」/「...」，这类值不能直接入库。"""
    v = (v or "").strip()
    return v.endswith("...") or v.endswith("…")


def _pick(row, pdf, key):
    """字段取值：列表优先（权威、不串页），被截断或为空时用**已校验过的**审签表 PDF 补全。"""
    v = (row.get(key) or "").strip()
    if v and not _truncated(v):
        return v
    pv = (pdf.get(key) or "").strip()
    return pv or v


def _amount(s):
    """金额：rd-web 写「168万元」「46449元」「/」。万元必须换算，否则 168 万被存成 168 元。"""
    s = (s or "").replace(",", "").strip()
    if not s or s == "/":
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None
    v = float(m.group(1))
    return v * 10000 if "万" in s else v


def _pdf_text(pdf_path):
    try:
        return subprocess.run(["pdftotext", "-raw", pdf_path, "-"],
                              capture_output=True, text=True, timeout=60).stdout or ""
    except Exception:
        return ""


def _name_key(name, n=10):
    """用项目名前若干字做「这条是不是本条」的判据。列表里长名会带尾部省略号，先剥掉。"""
    return re.sub(r"[\s.．…]+$", "", re.sub(r"\s+", "", name or ""))[:n]


def _pdf_matches(pdf_path, expect_name):
    """审签表 PDF 复核：里面的项目名必须和列表一致，否则是别人的单子，丢弃。"""
    t = _pdf_text(pdf_path).replace(" ", "").replace("\n", "")
    key = _name_key(expect_name, 12)
    return bool(key) and key in t


def _save_att(d, fname, path, category, replace=False):
    import shutil
    exist = db.session.execute(
        db.select(ProjectDistributionAttachment).filter_by(
            distribution_id=d.id, original_name=fname, category=category)).scalar_one_or_none()
    if exist and not replace:
        return
    saved = f"{d.id}_{category}_{os.path.basename(path)}"
    dst = os.path.join(_attach_dir(d.id), saved)
    shutil.copy(path, dst)
    if exist:                                   # 审签表：用校验过的新件覆盖旧件
        exist.saved_name = saved
        exist.file_size = os.path.getsize(dst)
        exist.uploaded_at = _now()
        return
    db.session.add(ProjectDistributionAttachment(
        distribution_id=d.id, category=category, original_name=fname, saved_name=saved,
        file_size=os.path.getsize(dst),
        mime_type="application/pdf" if fname.lower().endswith(".pdf") else "",
        uploaded_by=SOURCE_TAG, uploaded_at=_now()))


def _write_row(row, files, pdf_path, expect_name):
    """把一行写进项目池。字段以列表为准（权威、不串页），长字段被列表截断时用已校验的 PDF 补全。"""
    serial = row["流水号"]
    pdf = _parse_pdf_fields(pdf_path) if pdf_path else {}
    d = db.session.execute(
        db.select(ProjectDistribution).filter_by(serial_no=serial)).scalar_one_or_none()
    is_new = d is None
    if is_new:
        d = ProjectDistribution(serial_no=serial, source=SOURCE_TAG, status="待分发",
                                created_by=SOURCE_TAG, created_at=_now())
        db.session.add(d)
    d.officer = MY_OWNER
    # 这条是从**黄新博本人的待处理列表**里抓来的，就该归他的 4.0 项目池。
    # 老逻辑只按流水号找行、不改 source：早年通用抓取器(source=rd-web)建过的同一条，
    # 抓完仍挂在助理的 2.x 分发池里，**4.0 池按 source 过滤 → 看不见**（实测漏了 3 条：
    # 超声刀手柄线 / 透析型人工肾 / 压迫止血器）。故认领过来。
    d.source = SOURCE_TAG
    d.name = _pick(row, pdf, "项目名称") or d.name
    content = _pick(row, pdf, "项目基本情况")
    if content:
        d.content = content
    d.org_form = _pick(row, pdf, "采购组织形式") or d.org_form
    d.form_type = _pick(row, pdf, "项目所属分类") or d.form_type
    d.method = map_method(_pick(row, pdf, "采购方式")) or d.method
    if d.org_form in ("分散采购", "集中采购"):
        d.method = "政府采购"                     # 大类可靠信号优先
    d.budget = _amount(_pick(row, pdf, "预算金额")) or d.budget
    d.price_limit = _amount(_pick(row, pdf, "限价金额")) or d.price_limit
    d.manage_dept = _pick(row, pdf, "归口管理科室") or d.manage_dept
    d.demand_dept = _pick(row, pdf, "需求科室") or d.demand_dept
    # 项目编号**只认列表列**（rd-web 里多为空）：PDF 里该字段后面紧跟附件文件名，
    # 老解析器把文件名/别的值当成了编号（25QNMP080、xxx.xlsx 就是这么来的），
    # 故这里以列表为唯一真源、空就是空，顺带把历史脏值洗掉。
    pn = (row.get("项目编号") or "").strip()
    if not _truncated(pn):
        d.project_number = pn                 # 空就是空，顺带把历史脏值洗掉
    if row.get("发起人"):
        d.originator = row["发起人"]
    # 抓的就是「已分发给我的待处理审签表」，指定了经办人即等于已分发。
    # 漏了这步会一直挂在「待分发」，经办人看不到「立项」按钮（只在已分发时出现）。
    if d.officer and d.status == "待分发":
        d.status = "已分发"
    d.updated_at = _now()
    db.session.flush()
    for fname, path in files:
        try:
            _save_att(d, fname, path, "附件")
        except Exception:
            pass
    if pdf_path:
        try:
            _save_att(d, f"{serial}_审签表.pdf", pdf_path, "审签表", replace=True)
        except Exception:
            pass
    db.session.commit()
    return is_new


def import_my_pending():
    from playwright.sync_api import sync_playwright
    loginuser, password = _creds()
    state_path = _state_path(loginuser)
    tmp = tempfile.mkdtemp(prefix="rdmine_")
    imported = updated = skipped = 0
    errors, warns = [], []
    matched = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx_args = {"user_agent": UA, "accept_downloads": True,
                    "viewport": {"width": 1920, "height": 1080}}
        if os.path.exists(state_path):      # 复用会话，避免「登录太频繁」（爬虫不开人员弹框，可复用）
            ctx_args["storage_state"] = state_path
        ctx = browser.new_context(**ctx_args)
        pg = ctx.new_page()
        try:
            pg.goto(LOGIN_URL, wait_until="networkidle", timeout=45000)
            pg.wait_for_timeout(1500)
            if pg.locator("#loginBtn").count() and pg.locator("#loginBtn").first.is_visible():
                pg.fill("#loginUser", loginuser)
                pg.fill("#password", password)
                pg.click("#loginBtn")
                pg.wait_for_selector(f"text={WF_NAME}", timeout=25000)
                ctx.storage_state(path=state_path)
            if "登录太频繁" in pg.evaluate("()=>document.body.innerText"):
                raise RuntimeError("rd-web 提示「登录太频繁」，请稍后再试")
            pg.wait_for_selector(f"text={WF_NAME}", timeout=20000)
            pg.locator(f"text={WF_NAME}").first.click()
            pg.wait_for_timeout(2500)
            fr = None
            for _ in range(20):
                fr = next((f for f in pg.frames if APP_MARK in (f.url or "")), None)
                if fr and re.search(r"20\d{11}", fr.evaluate("()=>document.body.innerText") or ""):
                    break
                pg.wait_for_timeout(1000)
            if not fr:
                raise RuntimeError("未加载到审签表列表")

            # 分页：li.page 里带页码的 a（首页/尾页/«/» 不在 li.page 内）
            try:
                pages = [t.strip() for t in fr.locator(".pagination li.page a").all_inner_texts()]
                pages = [t for t in pages if t.isdigit()]
            except Exception:
                pages = []
            if not pages:
                pages = ["1"]
            pages = pages[:MAX_PAGES]

            seen = set()
            for pi, ptxt in enumerate(pages):
                if pi > 0:
                    first_before = ""
                    try:
                        rows0 = fr.evaluate(_ROWS_JS)
                        first_before = rows0[0]["流水号"] if rows0 else ""
                    except Exception:
                        pass
                    try:
                        fr.locator(".pagination li.page a", has_text=re.compile(rf"^{ptxt}$")
                                   ).first.click(timeout=8000)
                    except Exception:
                        try:
                            fr.locator(".pagination li.page a").nth(pi).click(timeout=8000)
                        except Exception:
                            warns.append(f"第{ptxt}页翻页失败")
                            break
                    ok = False
                    for _ in range(20):                # 等页面真的换了
                        pg.wait_for_timeout(600)
                        try:
                            rows0 = fr.evaluate(_ROWS_JS)
                        except Exception:
                            continue
                        if rows0 and rows0[0]["流水号"] != first_before:
                            ok = True
                            break
                    if not ok:
                        warns.append(f"第{ptxt}页内容未刷新，已跳过")
                        continue

                try:
                    rows = fr.evaluate(_ROWS_JS)
                except Exception as ex:
                    errors.append(f"第{ptxt}页读表失败：{str(ex)[:80]}")
                    continue

                todo = []
                for row in rows:
                    serial = row.get("流水号") or ""
                    if not re.match(r"^20\d{11}$", serial):
                        continue
                    if (row.get("当前节点") or "").strip() != MY_NODE:
                        skipped += 1
                        continue
                    if not row.get("_aligned"):
                        errors.append(f"{serial}: 列表列错位，未写入（请检查 rd-web 表头是否变动）")
                        continue
                    if serial in seen:
                        continue
                    todo.append(row)

                for row in todo:
                    if matched >= MAX_ITEMS:
                        break
                    serial = row["流水号"]
                    seen.add(serial)
                    matched += 1
                    name = (row.get("项目名称") or "").strip()
                    try:
                        files, pdf_path, warn = _download_item(pg, fr, serial, name, tmp)
                        if warn:
                            warns.append(f"{serial}: {warn}")
                        is_new = _write_row(row, files, pdf_path, name)
                        imported += (1 if is_new else 0)
                        updated += (0 if is_new else 1)
                    except Exception as ex:
                        db.session.rollback()
                        errors.append(f"{serial}: {str(ex)[:100]}")
                if matched >= MAX_ITEMS:
                    break
        finally:
            browser.close()
    return {"imported": imported, "updated": updated, "skipped": skipped,
            "errors": errors, "warns": warns, "matched": matched, "pages": len(pages)}


def run_async(app):
    def worker():
        with app.app_context():
            try:
                res = import_my_pending()
                msg = (f"抓取完成：{res['pages']} 页共处理 {res['matched']} 条，"
                       f"新增 {res['imported']}，更新 {res['updated']}，跳过 {res['skipped']}")
                if res.get("warns"):
                    msg += f"；{len(res['warns'])} 条附件未取（{res['warns'][0][:60]}）"
                if res.get("errors"):
                    msg += f"；{len(res['errors'])} 条出错（{res['errors'][0][:60]}）"
                _state["last_msg"] = msg
            except Exception as e:
                _state["last_msg"] = f"抓取出错：{e}"
            finally:
                _state["last_run"] = time.time()
                with _lock:
                    _state["running"] = False
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
    threading.Thread(target=worker, daemon=True).start()
    return True
