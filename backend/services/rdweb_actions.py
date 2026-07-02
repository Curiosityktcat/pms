"""rd-web 审签表「办理」动作（接收/驳回/撤回/指定经办人）——Playwright RPA。

与 rdweb_scraper 同套路：复用会话(storage_state)，跑 rd-web 自己的 JS（接口全加密，无法裸发）。
仅针对「采购需求审签表」的「采购部接收」节点。每个动作开一个无头 Chrome、办完即关。

⚠️ 接收/驳回 = 真实盖陈梦霞电子签名并推进流程，对外不可逆。调用方须先经用户二次确认。
办理流程（已实测，见 [[rdweb-scraper]]）：
  待处理列表单击行 → 「立即处理」→ 选「已接收/驳回」单选 →
  「采购部项目经办人」点开人员弹窗(展开采购部 iconCaret→勾选成员→确定) → 意见(选填) → 底部「确定」提交。
撤回：「已处理」页签打开该流水号 → 点「撤回」（无确认框）。
"""
import os
import re
import threading
import time

from models import db
from models.sys_config import SysConfig
from services import rdweb_scraper as R

WF = R.WORKFLOWS[0]  # 采购需求审签表

_lock = threading.Lock()
_state = {"running": False, "last_msg": "", "last_run": 0, "serial": "", "action": ""}


def status():
    return dict(_state)


def _cfg(key, default=""):
    row = db.session.get(SysConfig, key)
    return (row.value if row else "") or default


def _new_ctx(p):
    browser = p.chromium.launch(channel="chrome", headless=True,
                                args=["--no-sandbox", "--disable-dev-shm-usage"])
    ctx_args = {"user_agent": R.UA, "viewport": {"width": 1600, "height": 1000},
                "accept_downloads": True}
    if os.path.exists(R.STATE_PATH):
        ctx_args["storage_state"] = R.STATE_PATH
    return browser, browser.new_context(**ctx_args)


def _login_and_list(pg, ctx):
    """登录(必要时)→进采购需求审签表→返回列表 frame。"""
    pg.goto(R.LOGIN_URL, wait_until="networkidle", timeout=45000)
    pg.wait_for_timeout(1500)
    if pg.locator("#loginBtn").count() and pg.locator("#loginBtn").first.is_visible():
        pg.fill("#loginUser", _cfg("rdweb_loginuser"))
        pg.fill("#password", _cfg("rdweb_password"))
        pg.click("#loginBtn")
        pg.wait_for_selector(f"text={WF['name']}", timeout=25000)
        ctx.storage_state(path=R.STATE_PATH)
    if "登录太频繁" in pg.evaluate("()=>document.body.innerText"):
        raise RuntimeError("rd-web 提示「登录太频繁」，请稍后再试")
    pg.wait_for_selector(f"text={WF['name']}", timeout=20000)
    pg.locator(f"text={WF['name']}").first.click()
    pg.wait_for_timeout(2500)
    fr = None
    for _ in range(20):
        fr = next((f for f in pg.frames if WF["app_mark"] in (f.url or "")), None)
        if fr and re.search(r'20\d{11}', fr.evaluate("()=>document.body.innerText")):
            break
        pg.wait_for_timeout(1000)
    if not fr:
        raise RuntimeError("未加载到审签表列表")
    return fr


def _switch_tab(fr, pg, tab):
    try:
        fr.locator(f"text={tab}").first.click(timeout=5000)
    except Exception:
        pass
    pg.wait_for_timeout(2500)


def _open_row(fr, pg, serial, tries=3):
    """在当前页签找到流水号行并单击打开详情；找不到则重试（间歇性渲染慢）。"""
    for _ in range(tries):
        try:
            loc = fr.locator(f"text={serial}")
            if loc.count():
                loc.first.click(timeout=8000)
                pg.wait_for_timeout(3500)
                return True
        except Exception:
            pass
        pg.wait_for_timeout(2500)
    return False


def _click_anyframe(pg, text, timeout=6000):
    for f in pg.frames:
        try:
            loc = f.locator(f"text={text}")
            if loc.count():
                loc.first.click(timeout=timeout)
                return True
        except Exception:
            pass
    return False


def _pick_officer(pg, fr, officer):
    """点开「采购部项目经办人」人员弹窗→展开采购部→勾选 officer→确定。返回是否成功。"""
    fr.locator("xpath=//*[contains(text(),'采购部项目经办人')]/following::input[1]").first.click(timeout=5000)
    pg.wait_for_timeout(2500)
    dlg = None
    for f in pg.frames:
        try:
            if f.locator("input[placeholder*=姓名]").count():
                dlg = f
                break
        except Exception:
            pass
    if not dlg:
        return False
    # 展开「采购部」树
    dlg.evaluate("""()=>{
      const g=[...document.querySelectorAll('.groupName')].find(e=>{const s=e.querySelector('span');return s&&s.innerText.trim()==='采购部';});
      if(g){const c=g.querySelector('.iconCaret'); if(c) c.click();}
    }""")
    dlg.wait_for_timeout(1800)
    # 勾选目标成员：点其节点附近的选择按钮（排除 disable）
    picked = dlg.evaluate("""(name)=>{
      const leaf=[...document.querySelectorAll('*')].filter(e=>e.children.length<=2 && (e.innerText||'').trim()===name);
      if(!leaf.length) return false;
      const node=leaf[0];
      const box=node.closest('.userName,[class*=user],li,div')||node.parentElement;
      const btns=[...box.querySelectorAll('button')].filter(b=>!/disable/.test(b.className));
      if(btns.length){btns[0].click(); return true;}
      node.click(); return true;
    }""", officer)
    dlg.wait_for_timeout(1000)
    body = dlg.evaluate("()=>document.body.innerText")
    ok = ("已选择成员(1人)" in body) or ("已选择成员（1人）" in body)
    if ok or picked:
        # 弹窗确定（弹窗内的确定，通常在已选择面板下方）
        try:
            dlg.locator("text=确定").last.click(timeout=4000)
        except Exception:
            pass
        pg.wait_for_timeout(1500)
    # 校验经办人字段已填
    try:
        val = fr.locator("xpath=//*[contains(text(),'采购部项目经办人')]/following::input[1]").first.input_value()
        return bool(val.strip())
    except Exception:
        return ok


def _submit_form(fr, pg):
    """点表单底部「确定」提交（与「取消」并排，y 在最底部）。"""
    fr.evaluate("""()=>{
      const bs=[...document.querySelectorAll('button,a,[role=button]')]
        .filter(e=>(e.innerText||'').trim()==='确定' && e.getBoundingClientRect().width>0);
      // 取最靠下的那个 = 表单提交
      bs.sort((a,b)=>b.getBoundingClientRect().y-a.getBoundingClientRect().y);
      if(bs.length) bs[0].click();
    }""")
    pg.wait_for_timeout(3500)


def _do(action, serial, officer="", opinion=""):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser, ctx = _new_ctx(p)
        try:
            pg = ctx.new_page()
            fr = _login_and_list(pg, ctx)

            if action == "withdraw":
                _switch_tab(fr, pg, "已处理")
                if not _open_row(fr, pg, serial):
                    raise RuntimeError("已处理列表未找到该流水号")
                if not _click_anyframe(pg, "撤回"):
                    raise RuntimeError("未找到「撤回」按钮")
                pg.wait_for_timeout(2500)
                # 可能有确认框
                _click_anyframe(pg, "确定", timeout=3000)
                pg.wait_for_timeout(2500)
                _switch_tab(fr, pg, "待处理")
                back = serial in fr.evaluate("()=>document.body.innerText")
                return {"ok": back, "msg": "撤回成功，已回到待处理" if back else "撤回后未在待处理找到，请人工核对"}

            # accept / reject
            _switch_tab(fr, pg, "待处理")
            if not _open_row(fr, pg, serial):
                raise RuntimeError("待处理列表未找到该流水号（可能已被处理）")
            if not _click_anyframe(pg, "立即处理"):
                raise RuntimeError("未找到「立即处理」")
            pg.wait_for_timeout(5000)
            choice = "已接收" if action == "accept" else "驳回"
            try:
                fr.locator(f"text={choice}").first.click(timeout=5000)
            except Exception:
                raise RuntimeError(f"未找到「{choice}」单选")
            pg.wait_for_timeout(600)
            if action == "accept":
                if not officer:
                    raise RuntimeError("接收必须指定经办人")
                if not _pick_officer(pg, fr, officer):
                    raise RuntimeError(f"经办人「{officer}」选择失败")
            if opinion:
                try:
                    fr.locator("xpath=//*[contains(text(),'意见')]/following::textarea[1]").first.fill(opinion)
                except Exception:
                    pass
            _submit_form(fr, pg)
            # 校验：从待处理消失即视为提交成功
            _switch_tab(fr, pg, "待处理")
            gone = serial not in fr.evaluate("()=>document.body.innerText")
            verb = "接收" if action == "accept" else "驳回"
            return {"ok": gone,
                    "msg": f"{verb}成功" + (f"（经办人：{officer}）" if action == "accept" else "")
                           if gone else f"{verb}后仍在待处理，请人工核对是否提交成功"}
        finally:
            browser.close()


def _sync_local(action, serial, officer):
    """办理成功后同步本地「项目分发」记录状态/经办人。"""
    from models.project_distribution import ProjectDistribution
    d = db.session.execute(
        db.select(ProjectDistribution).filter_by(serial_no=serial)
    ).scalar_one_or_none()
    if not d:
        return
    if action == "accept":
        d.status, d.officer = "已分发", officer
    elif action == "reject":
        d.status = "已驳回"
    elif action == "withdraw":
        d.status, d.officer = "待分发", ""
    d.updated_at = _now()
    db.session.commit()


def _now():
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")


def run_async(app, action, serial, officer="", opinion=""):
    def worker():
        with app.app_context():
            try:
                res = _do(action, serial, officer, opinion)
                _state["last_msg"] = res["msg"]
                _state["ok"] = res["ok"]
                if res["ok"]:
                    try:
                        _sync_local(action, serial, officer)
                    except Exception:
                        pass
            except Exception as e:
                _state["last_msg"] = f"{action} 出错：{str(e)[:140]}"
                _state["ok"] = False
            finally:
                _state.update(running=False, last_run=time.time())
    with _lock:
        if _state["running"]:
            return False
        _state.update(running=True, serial=serial, action=action, last_msg="", ok=None)
    threading.Thread(target=worker, daemon=True).start()
    return True
