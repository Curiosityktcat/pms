"""rd-web（医互通）采购需求审签表 自动抓取 → 写入「项目分发」。

技术：Playwright 无头系统 Chrome 跑 rd-web 自己的 JS（绕过 RSA 登录/WAF/加密响应）。
要点：**复用登录会话**（storage_state），仅会话失效时才重新登录，避免触发「登录太频繁」。
凭据存 SysConfig：rdweb_loginuser / rdweb_password。
节流：手动刷新 30 分钟一次（由路由层用 SysConfig rdweb_last_scrape_at 控制）。
"""
import os
import re
import json
import threading
import datetime

from models import db
from models.sys_config import SysConfig
from models.agency import Agency  # noqa: F401 (确保模型注册)
from models.project_distribution import ProjectDistribution, ProjectDistributionAttachment

LOGIN_URL = "https://rd-web.mobimedical.cn/"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0 Safari/537.36")
STATE_PATH = os.path.expanduser("~/pms/.rdweb_session.json")
UPLOAD_ROOT = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "uploads", "project_distribution"))

# 三个需要分发的流程。各表单字段不同，用 JSON(extra) 照搬全部字段；
# node = 该表单里"轮到陈梦霞/采购部分发"的节点关键词（用于筛待办）；
# title = 用作项目名的字段；officer = 默认指定经办人。
WORKFLOWS = [
    {"name": "采购需求审签表", "app_mark": "appUpgrade/app/65f2acb",
     "form_type": "采购需求审签表", "node": "采购部接收", "title": "项目名称", "officer": ""},
    {"name": "设备科维修及资金使用（启动项目）流程", "app_mark": "appUpgrade/app/6200d3d4",
     "form_type": "设备科维修", "node": "采购部", "title": "设备名称或设备型号", "officer": "杨文炽"},
    {"name": "医用耗材紧急临时需求及审批表", "app_mark": "appUpgrade/app/68a3e253",
     "form_type": "医用耗材紧急", "node": "采购部", "title": "耗材通用名", "officer": "郑跃俊"},
]

_lock = threading.Lock()
_state = {"running": False, "last_msg": "", "last_run": 0}


def _cfg(key, default=""):
    row = db.session.get(SysConfig, key)
    return (row.value if row else "") or default


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _parse_amount(s):
    m = re.search(r'([\d]+(?:\.\d+)?)', (s or "").replace(",", ""))
    return float(m.group(1)) if m else None


def map_method(s):
    s = s or ""
    if "竞选" in s:
        return "院内竞选"
    if "单一来源" in s:
        return "院内单一来源采购"
    if "询价" in s:
        return "院内询价"
    if "议价" in s:
        return "院内议价"
    if "紧急" in s:
        return "医用耗材紧急采购"
    if "政府采购" in s:
        return "政府采购"
    return s.strip()


def _parse_print(text):
    """从「流程打印」页纯文本解析字段。该页是干净的 `标签\\t值` 逐行格式
    （无列表表头干扰），空值（如项目编号）也能正确为空。字段区到审批流程(开始)即止；
    并从流程首节点抓「发起人」（形如 `姓名\\t开始`）。"""
    lines = (text or "").split("\n")
    out = {}
    in_fields = True
    for idx, ln in enumerate(lines):
        if ln.strip() == "开始":   # 字段区结束、进入审批流程节点
            in_fields = False
            for j in range(idx + 1, min(idx + 4, len(lines))):
                m = re.match(r'^(\S+)\t开始\s*$', lines[j])
                if m:
                    out["发起人"] = m.group(1).strip()
                    break
            continue
        # 通用：抓取字段区内全部 `标签\t值`（照搬该表单所有字段）
        if in_fields and "\t" in ln:
            k, _, v = ln.partition("\t")
            k = k.strip()
            if k and k not in out and k not in ("流水号", "当前节点", "当前处理人", "发起时间"):
                out[k] = v.strip()
    return out


def _attach_dir(did):
    d = os.path.join(UPLOAD_ROOT, str(did))
    os.makedirs(d, exist_ok=True)
    return d


# ── Playwright 抓取某个流程（返回 [dict(...含 _files、_print_pdf)]）──────────────
def _scrape(wf, target_serial=None):
    from playwright.sync_api import sync_playwright
    loginuser = _cfg("rdweb_loginuser")
    password = _cfg("rdweb_password")
    if not (loginuser and password):
        raise RuntimeError("未配置 rd-web 账号（SysConfig rdweb_loginuser / rdweb_password）")
    import tempfile
    tmp = tempfile.mkdtemp(prefix="rdweb_")
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True,
                                    args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx_args = {"user_agent": UA, "accept_downloads": True}
        if os.path.exists(STATE_PATH):
            ctx_args["storage_state"] = STATE_PATH
        ctx = browser.new_context(**ctx_args)
        pg = ctx.new_page()
        pg.goto(LOGIN_URL, wait_until="networkidle", timeout=45000)
        pg.wait_for_timeout(1500)
        # 会话失效（出现登录框）→ 重新登录
        if pg.locator("#loginBtn").count() and pg.locator("#loginBtn").first.is_visible():
            pg.fill("#loginUser", loginuser)
            pg.fill("#password", password)
            pg.click("#loginBtn")
            pg.wait_for_selector(f"text={wf['name']}", timeout=25000)
            ctx.storage_state(path=STATE_PATH)
        body = pg.evaluate("()=>document.body.innerText")
        if "登录太频繁" in body:
            browser.close()
            raise RuntimeError("rd-web 提示「登录太频繁」，请稍后再试")
        pg.wait_for_selector(f"text={wf['name']}", timeout=20000)
        pg.locator(f"text={wf['name']}").first.click()
        pg.wait_for_timeout(2000)
        fr = None
        for _ in range(20):
            fr = next((f for f in pg.frames if wf["app_mark"] in (f.url or "")), None)
            if fr:
                try:
                    if re.search(r'20\d{11}', fr.evaluate("()=>document.body.innerText")):
                        break
                except Exception:
                    pass
            pg.wait_for_timeout(1000)
        if not fr:
            browser.close()
            raise RuntimeError(f"未加载到「{wf['name']}」列表")
        # 列表行 → 流水号。只取处于本流程"采购部分发"节点（wf['node']）的待处理项。
        rows = fr.eval_on_selector_all(
            "tr,[class*=row],[class*=item]",
            "els=>els.map(e=>e.innerText.replace(/\\n/g,' ').replace(/\\s+/g,' ').trim())"
            ".filter(t=>/20\\d{11}/.test(t))")
        items = []
        for t in rows:
            sm = re.search(r'(20\d{11})', t)
            if not sm:
                continue
            serial = sm.group(1)
            if wf["node"] and wf["node"] not in t:
                continue
            if serial in items:
                continue
            items.append(serial)
        if target_serial:
            items = [s for s in items if s == target_serial]
        for serial in items:
            try:
                fr.locator(f"text={serial}").first.click(timeout=8000)
                pg.wait_for_timeout(6000)
                dfr = fr
                for f in pg.frames:
                    try:
                        if "下载" in f.evaluate("()=>document.body.innerText") and serial in f.evaluate("()=>document.body.innerText"):
                            dfr = f
                    except Exception:
                        pass
                fields = {}
                files = []
                dl = dfr.locator("text=下载")
                for i in range(dl.count()):
                    try:
                        with pg.expect_download(timeout=20000) as di:
                            dl.nth(i).click()
                        d = di.value
                        path = os.path.join(tmp, f"{serial}_{i}_{d.suggested_filename}")
                        d.save_as(path)
                        files.append((d.suggested_filename, path))
                    except Exception:
                        pass
                # 流程打印 PDF（审签表）：点「流程打印」开新页 → 等异步渲染 → page.pdf
                pdf_path = None
                try:
                    with ctx.expect_page(timeout=12000) as pinfo:
                        dfr.locator("text=流程打印").first.click(timeout=8000)
                    np = pinfo.value
                    try:
                        np.wait_for_load_state("networkidle", timeout=20000)
                    except Exception:
                        pass
                    np.wait_for_timeout(3000)  # 等表单数据异步填充
                    # 从这张干净的打印页解析全字段（避开列表表头干扰）
                    try:
                        fields = _parse_print(np.evaluate("()=>document.body.innerText")) or fields
                    except Exception:
                        pass
                    pdf_path = os.path.join(tmp, f"{serial}_审签表.pdf")
                    np.pdf(path=pdf_path, format="A4", print_background=True,
                           margin={"top": "8mm", "bottom": "8mm", "left": "8mm", "right": "8mm"})
                    np.close()
                    if os.path.getsize(pdf_path) < 2000:  # 太小说明没渲染出来
                        pdf_path = None
                except Exception:
                    pdf_path = None
                results.append({"serial_no": serial, "fields": fields,
                                "_files": files, "_print_pdf": pdf_path})
                # 关闭详情，回列表
                try:
                    dfr.locator("text=×").first.click(timeout=3000)
                except Exception:
                    pass
                pg.wait_for_timeout(1500)
            except Exception as ex:
                results.append({"serial_no": serial, "error": str(ex)[:120], "_files": []})
        browser.close()
    return results


# ── 抓取 + 写入项目分发（遍历三个流程）────────────────────────────────
def _save_att(d, fname, path, category):
    """保存一个附件（同名同类已存在则跳过）。"""
    import shutil
    exist = db.session.execute(
        db.select(ProjectDistributionAttachment).filter_by(
            distribution_id=d.id, original_name=fname, category=category)
    ).scalar_one_or_none()
    if exist:
        return
    saved = f"{d.id}_{category}_{os.path.basename(path)}"
    dst = os.path.join(_attach_dir(d.id), saved)
    shutil.copy(path, dst)
    db.session.add(ProjectDistributionAttachment(
        distribution_id=d.id, category=category, original_name=fname, saved_name=saved,
        file_size=os.path.getsize(dst),
        mime_type="application/pdf" if fname.lower().endswith(".pdf") else "",
        uploaded_by=source_tag_default(), uploaded_at=_now()))


def source_tag_default():
    return "rd-web"


def import_pending(target_serial=None, source_tag="rd-web", only_form_type=None):
    """遍历三个流程抓取待分发项并写入项目分发（按流水号去重/更新）。返回 summary。"""
    import json as _json
    imported, updated, errors = 0, 0, []
    for wf in WORKFLOWS:
        if only_form_type and wf["form_type"] != only_form_type:
            continue
        try:
            scraped = _scrape(wf, target_serial)
        except Exception as e:
            errors.append(f"{wf['form_type']}: {str(e)[:120]}")
            continue
        for r in scraped:
            serial = r.get("serial_no")
            if r.get("error"):
                errors.append(f"{serial}: {r['error']}")
                continue
            f = r.get("fields", {})
            d = db.session.execute(
                db.select(ProjectDistribution).filter_by(serial_no=serial)
            ).scalar_one_or_none()
            is_new = d is None
            if is_new:
                d = ProjectDistribution(serial_no=serial, source=source_tag, status="待分发",
                                        created_by=source_tag, created_at=_now())
                db.session.add(d)
            if f:
                d.form_type = wf["form_type"]
                d.originator = f.get("发起人", "") or d.originator
                d.name = f.get(wf["title"], "") or d.name  # 该流程的标题字段作项目名
                if not d.officer and wf["officer"]:
                    d.officer = wf["officer"]  # 默认经办人
                # 采购需求审签表：另填通用列（其它流程这些列留空，全字段在 extra）
                if wf["form_type"] == "采购需求审签表":
                    d.content = f.get("项目基本情况", "")
                    d.budget = _parse_amount(f.get("预算金额"))
                    d.price_limit = _parse_amount(f.get("限价金额"))
                    d.method = map_method(f.get("采购方式", ""))
                    d.org_form = f.get("采购组织形式", "")
                    d.manage_dept = f.get("归口管理科室", "")
                    d.demand_dept = f.get("需求科室", "")
                    d.project_number = f.get("项目编号", "")
                # 照搬该表单全部字段到 extra（去发起人，前端动态展示）
                d.extra = _json.dumps({k: v for k, v in f.items() if k != "发起人"},
                                      ensure_ascii=False)
            d.updated_at = _now()
            db.session.flush()
            for fname, path in r.get("_files", []):
                try:
                    _save_att(d, fname, path, "附件")
                except Exception:
                    pass
            if r.get("_print_pdf"):
                try:
                    _save_att(d, f"{serial}_审签表.pdf", r["_print_pdf"], "审签表")
                except Exception:
                    pass
            db.session.commit()
            if is_new:
                imported += 1
            else:
                updated += 1
    return {"imported": imported, "updated": updated, "errors": errors}


def run_async(app, target_serial=None):
    """后台线程跑抓取（供路由触发）。"""
    def worker():
        with app.app_context():
            try:
                res = import_pending(target_serial)
                _state["last_msg"] = (f"抓取完成：新增 {res['imported']}，更新 {res['updated']}"
                                      + (f"，{len(res['errors'])} 条出错" if res['errors'] else ""))
            except Exception as e:
                _state["last_msg"] = f"抓取出错：{e}"
            finally:
                _state["last_run"] = __import__("time").time()
                with _lock:
                    _state["running"] = False
    with _lock:
        if _state["running"]:
            return False
        _state["running"] = True
    threading.Thread(target=worker, daemon=True).start()
    return True
