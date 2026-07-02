"""rd-web 采购项目审批流程 自动提交。

表单字段（实测）：
  forvalue[0] → 采购部经办人（人员选择框触发 input）
  forvalue[1] → 归口管理科室
  forvalue[2] → 项目名称
  button.item-drop-box-btn → 项目资料名称（自定义下拉）
  添加附件 → 资料上传
  经办人 showNames 人员弹窗 → 采购部经办人

APP_MARK: 65fb995ac1478c1a9b75064c
"""
import os
import re
import time

LOGIN_URL   = "https://rd-web.mobimedical.cn/"
APP_MARK    = "65fb995ac1478c1a9b75064c"
SESSION_DIR = os.path.expanduser("~/pms")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _state_path(loginuser: str) -> str:
    safe = re.sub(r"[^\w]", "_", loginuser)
    return os.path.join(SESSION_DIR, f".rdweb_session_{safe}.json")


# ── 内部步骤 ─────────────────────────────────────────────────────────────

def _wait_frame(pg, timeout_s=25):
    for _ in range(timeout_s):
        fr = next((f for f in pg.frames if APP_MARK in (f.url or "")), None)
        if fr:
            try:
                if fr.evaluate("()=>document.body.innerText").strip():
                    return fr
            except Exception:
                pass
        time.sleep(1)
    raise RuntimeError("超时：未加载到采购项目审批 frame")


def _login_if_needed(pg, ctx, loginuser, password, state_path):
    pg.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    pg.wait_for_timeout(4000)
    if pg.locator("#loginBtn").count() and pg.locator("#loginBtn").is_visible():
        pg.fill("#loginUser", loginuser)
        pg.fill("#password", password)
        pg.click("#loginBtn")
        pg.wait_for_timeout(4000)
        ctx.storage_state(path=state_path)
    body = pg.evaluate("()=>document.body.innerText")
    if "登录太频繁" in body:
        raise RuntimeError("rd-web 提示「登录太频繁」，请稍后重试")


def _nav_to_approval(pg):
    """点击左侧「采购项目审批流程」菜单，返回对应 frame。"""
    clicked = pg.evaluate("""() => {
        const el = [...document.querySelectorAll('*')].find(e =>
            (e.innerText||'').trim() === '采购项目审批流程'
            && e.getBoundingClientRect().width > 0);
        if (el) { el.click(); return true; }
        return false;
    }""")
    if not clicked:
        raise RuntimeError("未找到「采购项目审批流程」菜单")
    pg.wait_for_timeout(4000)
    return _wait_frame(pg)


def _open_form(fr, pg):
    """点「发起」，等待表单出现。"""
    fr.evaluate("""() => {
        const el = [...document.querySelectorAll('*')].find(e =>
            e.children.length <= 2 && (e.innerText||'').trim() === '发起'
            && e.getBoundingClientRect().width > 0);
        if (el) el.click();
    }""")
    for _ in range(20):
        pg.wait_for_timeout(500)
        ok = fr.evaluate("""() => {
            const t = document.body.innerText;
            return t.includes('项目名称') && t.includes('存草稿');
        }""")
        if ok:
            return
    raise RuntimeError("点击「发起」后等待表单超时")


def _visible_forvalue_inputs(fr):
    """返回表单中所有可见的 ng-model=forvalue input 列表（过滤 ng-hide）。"""
    all_loc = fr.locator('input[ng-model="forvalue"]')
    result = []
    for i in range(all_loc.count()):
        loc = all_loc.nth(i)
        try:
            if loc.is_visible(timeout=300):
                result.append(loc)
        except Exception:
            pass
    return result


def _fill_forvalue(fr, pg, idx, value):
    """填写第 idx 个可见的 ng-model=forvalue input（跳过 ng-hide 隐藏元素）。"""
    visible = _visible_forvalue_inputs(fr)
    if idx >= len(visible):
        raise RuntimeError(f"可见 forvalue input 只有 {len(visible)} 个，索引 {idx} 越界")
    inp = visible[idx]
    inp.click(timeout=3000)
    pg.wait_for_timeout(300)
    inp.fill(str(value), timeout=3000)
    pg.wait_for_timeout(200)


def _select_material_type(fr, pg, option_text):
    """点开「项目资料名称」下拉，选含 option_text 的选项。"""
    btn = fr.locator("button.item-drop-box-btn")
    if not btn.count() or not btn.is_visible(timeout=3000):
        raise RuntimeError("未找到「项目资料名称」下拉按钮（item-drop-box-btn）")
    btn.click(timeout=3000)
    pg.wait_for_timeout(1000)

    # 找含目标文字的 li 选项
    option = fr.locator(f"li.ng-scope:has-text('{option_text}')")
    if not option.count():
        # 列举所有 li 帮助调试
        all_li = fr.evaluate("""() =>
            [...document.querySelectorAll('li.ng-scope')]
                .filter(e => e.getBoundingClientRect().width > 0)
                .map(e => (e.innerText||'').trim())
        """)
        raise RuntimeError(
            f"未找到含「{option_text}」的选项，可用选项：{all_li}"
        )
    option.first.click(timeout=3000)
    pg.wait_for_timeout(500)


def _fill_officer(fr, pg, officer):
    """填写采购部经办人：展开部门树 → 点 selectPersonBtn → 确定。"""
    visible = _visible_forvalue_inputs(fr)
    if not visible:
        raise RuntimeError("未找到可见的经办人输入框")
    officer_inp = visible[0]
    officer_inp.click(timeout=5000)
    pg.wait_for_timeout(1500)

    pg.locator('input[placeholder="输入查找的姓名"]').wait_for(state="visible", timeout=8000)
    pg.wait_for_timeout(500)

    def _click_select_btn(name):
        pos = pg.evaluate(f"""() => {{
            const name = {repr(name)};
            let nameY = -1;
            for (const e of document.querySelectorAll('*')) {{
                const t = (e.innerText || '').trim();
                if (t !== name) continue;
                const r = e.getBoundingClientRect();
                if (r.width === 0 || r.height === 0 || r.y < 140 || r.x > 850) continue;
                nameY = r.y + r.height / 2;
                break;
            }}
            if (nameY < 0) return null;
            for (const btn of document.querySelectorAll('button.selectPersonBtn')) {{
                const r = btn.getBoundingClientRect();
                if (Math.abs(r.y + r.height / 2 - nameY) > 15) continue;
                if (r.width === 0 || r.height === 0) continue;
                return {{x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)}};
            }}
            return null;
        }}""")
        if not pos:
            return False
        pg.mouse.click(pos['x'], pos['y'])
        pg.wait_for_timeout(600)
        return True

    def _expand_next_caret():
        return pg.evaluate("""() => {
            for (const e of document.querySelectorAll('i')) {
                const cls = e.className || '';
                if (!cls.includes('Caret') && !cls.includes('caret-right')) continue;
                const r = e.getBoundingClientRect();
                if (r.x < 550 || r.x > 900 || r.y < 140) continue;
                if (r.width === 0 || r.height === 0) continue;
                e.click();
                return true;
            }
            return false;
        }""")

    _expand_next_caret()
    pg.wait_for_timeout(1500)
    found = _click_select_btn(officer)

    if not found:
        for _ in range(8):
            if not _expand_next_caret():
                break
            pg.wait_for_timeout(1000)
            if _click_select_btn(officer):
                found = True
                break

    if not found:
        pg.screenshot(path="/tmp/officer_not_found.png")
        raise RuntimeError(f"人员选择框中未找到「{officer}」（截图 /tmp/officer_not_found.png）")

    pg.locator('button:has-text("确定")').last.click(timeout=5000)
    pg.wait_for_timeout(1000)


def _upload_attachments(fr, pg, attachments):
    """逐个上传附件（复用 contract_submit 的 _upload_one 逻辑）。"""
    import mimetypes as _mt

    for item in attachments:
        file_path    = item["path"]
        display_name = item["name"]
        if not os.path.exists(file_path):
            raise RuntimeError(f"附件文件不存在: {file_path}")

        # 点「添加附件」
        add_btn = fr.locator("[class*='item-customer-add']")
        if not add_btn.count() or not add_btn.first.is_visible(timeout=2000):
            add_btn = fr.get_by_text("添加附件").first
        add_btn.click(timeout=5000)
        pg.wait_for_timeout(2000)

        # 找「上传附件」按钮（先主页面再 iframe）
        upload_btn = pg.locator("button.popshowfileuploadBtn")
        if not upload_btn.count() or not upload_btn.is_visible(timeout=4000):
            upload_btn = fr.locator("button.popshowfileuploadBtn")
            if not upload_btn.count() or not upload_btn.is_visible(timeout=4000):
                pg.screenshot(path="/tmp/approval_upload_debug.png")
                raise RuntimeError(
                    f"上传「{display_name}」时未找到「上传附件」按钮，"
                    "已截图 /tmp/approval_upload_debug.png"
                )

        mime = _mt.guess_type(display_name)[0] or "application/octet-stream"
        with open(file_path, "rb") as f:
            buf = f.read()

        with pg.expect_file_chooser(timeout=6000) as fc_info:
            upload_btn.click(timeout=3000)
        fc_info.value.set_files([{"name": display_name, "mimeType": mime, "buffer": buf}])

        # 等文件名出现
        for _ in range(20):
            pg.wait_for_timeout(1000)
            for container in [pg.locator(".ui-dialog").first, fr.locator(".ui-dialog").first]:
                try:
                    if display_name in container.inner_text(timeout=800):
                        break
                except Exception:
                    pass
            else:
                continue
            break

        # 点「确定」
        confirm = pg.locator("button.popConfirm")
        if confirm.count() and confirm.is_visible(timeout=3000):
            confirm.click(timeout=5000)
        else:
            try:
                pg.locator('.ui-dialog button:has-text("确定")').first.click(timeout=5000)
            except Exception:
                fr.locator('.ui-dialog button:has-text("确定")').first.click(timeout=5000)

        try:
            pg.locator("div.ui-widget-overlay").wait_for(state="hidden", timeout=8000)
        except Exception:
            pass
        pg.wait_for_timeout(800)


def _submit(fr, pg):
    """点最下方「提交」按钮，等表单关闭，读流水号。"""
    submit_btns = fr.locator("button,a,[role=button]").all()
    target = None
    max_y = -1
    for btn in submit_btns:
        try:
            if not btn.is_visible(timeout=200):
                continue
            if (btn.inner_text() or "").strip() != "提交":
                continue
            box = btn.bounding_box()
            if box and box["y"] > max_y:
                max_y = box["y"]
                target = btn
        except Exception:
            pass

    if not target:
        raise RuntimeError("未找到可见的「提交」按钮")

    target.click(timeout=5000)
    pg.wait_for_timeout(3000)

    ERROR_KWS = ["必填", "不能为空", "请填写", "请上传", "不可为空", "请选择", "校验失败"]

    def _fr_text():
        try:
            return fr.evaluate("()=>document.body.innerText")
        except Exception:
            return ""

    # 等表单关闭（最多 12 秒）
    form_closed = False
    for _ in range(12):
        pg.wait_for_timeout(1000)
        t = _fr_text()
        if "存草稿" not in t:
            form_closed = True
            break
        for kw in ERROR_KWS:
            if kw in t:
                lines = [l.strip() for l in t.split("\n") if kw in l and l.strip()]
                return {"ok": False, "msg": f"表单校验失败: {lines[0][:80] if lines else kw}"}

    if not form_closed:
        pg.screenshot(path="/tmp/approval_submit_timeout.png")
        return {"ok": False,
                "msg": "点提交后表单未关闭，可能存在校验错误（截图 /tmp/approval_submit_timeout.png）",
                "page_text": _fr_text()[:400]}

    # 切到「我发起的」标签读流水号
    pg.wait_for_timeout(1000)
    try:
        tab = fr.get_by_text("我发起的", exact=True).first
        if tab.is_visible(timeout=3000):
            tab.click(timeout=3000)
            pg.wait_for_timeout(3000)
    except Exception:
        pass

    for _ in range(8):
        t = _fr_text()
        for m in re.finditer(r"\b(\d{13})\b", t):
            num = m.group(1)
            if num.startswith("20"):
                return {"ok": True, "serial_no": num}
        m = re.search(r"\b(20\d{9,13})\b", t)
        if m:
            return {"ok": True, "serial_no": m.group(1)}
        pg.wait_for_timeout(1000)

    return {"ok": True, "serial_no": "", "msg": "表单已提交（流水号待从列表获取）"}


# ── 主入口 ───────────────────────────────────────────────────────────────

def submit_approval(
    manage_dept: str,
    project_name_text: str,    # 填入「项目名称」的文字
    material_type: str,        # 项目资料名称下拉选项（含此文字即可）
    officer: str,
    attachments: list = None,  # [{"path": str, "name": str}]
    loginuser: str = "13029144451",
    password: str  = "whywhy123",
) -> dict:
    """
    提交采购项目审批流程表单。

    attachments: 列表，每项 {"path": 文件绝对路径, "name": 展示文件名}
    返回：{"ok": bool, "serial_no": str, "msg": str, "detail": dict}
    """
    from playwright.sync_api import sync_playwright

    detail = {}
    attachments = attachments or []
    state_path = _state_path(loginuser)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx_kwargs = {
            "user_agent": UA,
            "viewport": {"width": 1920, "height": 1080},
            "accept_downloads": True,
        }
        if os.path.exists(state_path):
            ctx_kwargs["storage_state"] = state_path

        ctx = browser.new_context(**ctx_kwargs)
        pg  = ctx.new_page()

        try:
            # 1. 登录
            _login_if_needed(pg, ctx, loginuser, password, state_path)

            # 2. 导航到采购项目审批流程
            fr = _nav_to_approval(pg)

            # 3. 打开新建表单
            _open_form(fr, pg)
            pg.wait_for_timeout(800)

            # 4. 归口管理科室（forvalue[1]）
            if manage_dept:
                _fill_forvalue(fr, pg, 1, manage_dept)
                detail["manage_dept"] = manage_dept

            # 5. 项目名称（forvalue[2]）
            _fill_forvalue(fr, pg, 2, project_name_text)
            detail["project_name_text"] = project_name_text
            pg.wait_for_timeout(200)

            # 6. 项目资料名称下拉
            _select_material_type(fr, pg, material_type)
            detail["material_type"] = material_type

            # 7. 上传附件
            if attachments:
                _upload_attachments(fr, pg, attachments)
                detail["upload_count"] = len(attachments)

            # 8. 采购部经办人（人员选择）
            if officer:
                _fill_officer(fr, pg, officer)
                detail["officer"] = officer
                pg.wait_for_timeout(300)

            # 9. 提交
            result = _submit(fr, pg)
            detail["submit"] = result

            ctx.storage_state(path=state_path)
            browser.close()
            return {
                "ok":        result["ok"],
                "serial_no": result.get("serial_no", ""),
                "msg":       result.get("msg", ""),
                "detail":    detail,
            }

        except Exception as e:
            try:
                ctx.storage_state(path=state_path)
                browser.close()
            except Exception:
                pass
            return {"ok": False, "msg": str(e), "serial_no": "", "detail": detail}
