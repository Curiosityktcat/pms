"""rd-web 合同审签单自动提交。

填写策略：全部用 Playwright 原生 locator + fill()，而非 JS 直接赋值。
AngularJS 的 ng-model 只响应真实浏览器事件（focus / input / change），
NativeInputValueSetter 触发不了它的 $watch，所以必须用 Playwright 的
fill() / click() 来驱动输入。
"""
import os
import re
import time

LOGIN_URL    = "https://rd-web.mobimedical.cn/"
APP_MARK     = "6642c01d66eb836a97bbccb2"
SESSION_DIR  = os.path.expanduser("~/pms")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _state_path(loginuser: str) -> str:
    safe = re.sub(r"[^\w]", "_", loginuser)
    return os.path.join(SESSION_DIR, f".rdweb_session_{safe}.json")

CATEGORY_IDX = {
    "采购部合同": 0,
    "其他合同": 1,
    "其他合同（已授权的简化流程）": 2,
}

TEXT_FIELDS = [
    "合同名称", "合同编码", "项目名称及包号", "归口管理科室", "合同金额",
    "合同甲方", "甲方法定代表人", "甲方联系电话", "甲方地址",
    "合同乙方", "乙方法定代表人", "乙方联系电话", "乙方地址",
]


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
    raise RuntimeError("超时：未加载到合同审签单 frame")


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


def _nav_to_contract(pg):
    clicked = pg.evaluate("""() => {
        const el = [...document.querySelectorAll('*')].find(e =>
            e.children.length <= 3 && e.innerText.trim() === '合同审签单'
            && e.getBoundingClientRect().width > 0);
        if (el) { el.click(); return true; }
        return false;
    }""")
    if not clicked:
        raise RuntimeError("未找到「合同审签单」菜单")
    pg.wait_for_timeout(4000)
    return _wait_frame(pg)


def _open_form(fr, pg):
    """点「发起」，等待表单弹出。"""
    fr.evaluate("""() => {
        const el = [...document.querySelectorAll('*')].find(e =>
            e.children.length <= 2 && e.innerText.trim() === '发起'
            && e.getBoundingClientRect().width > 0);
        if (el) el.click();
    }""")
    # 等待表单出现（含「合同名称」和「提交」两个关键词）
    for _ in range(20):
        pg.wait_for_timeout(500)
        ok = fr.evaluate("""()=>{
            const t = document.body.innerText;
            return t.includes('合同名称') && t.includes('提交') && t.includes('存草稿');
        }""")
        if ok:
            return
    raise RuntimeError("点击「发起」后等待表单超时")


def _find_input_by_label(fr, label_text):
    """通过标签文字（忽略 * 号）在 iframe 里找对应的 input[placeholder='请输入']，
    返回坐标 {x, y} 或 None。ri.y > 60 排除顶部搜索栏（y≈55）。"""
    return fr.evaluate(f"""() => {{
        const target = {repr(label_text)};
        for (const e of document.querySelectorAll('*')) {{
            const raw = (e.innerText || '').trim();
            const txt = raw.replace(/\\*/g, '').trim();
            if (txt !== target) continue;
            const r = e.getBoundingClientRect();
            if (r.width === 0 || r.height === 0 || r.height > 50) continue;
            let p = e.parentElement;
            for (let i = 0; i < 6 && p; i++, p = p.parentElement) {{
                const inp = p.querySelector('input[placeholder="请输入"]');
                if (inp) {{
                    const ri = inp.getBoundingClientRect();
                    if (ri.width > 0 && ri.height > 0 && ri.y > 60)
                        return {{x: Math.round(ri.x + ri.width / 2),
                                 y: Math.round(ri.y + ri.height / 2)}};
                }}
            }}
        }}
        return null;
    }}""")


def _fill_text_fields(fr, pg, field_values):
    """按标签名填写文本字段。

    用 JS scrollIntoView + focus 代替 mouse.click，规避两个已知问题：
    1. 顶部搜索栏 input（y≈55）与表单 input 标签重名 → 加 ri.y>60 过滤
    2. 乙方地址 (frame y≈1099) 超出 1080px viewport → scrollIntoView 滚入后 focus
    """
    filled = []
    for label, value in zip(TEXT_FIELDS, field_values):
        ok = fr.evaluate(f"""() => {{
            const target = {repr(label)};
            for (const e of document.querySelectorAll('*')) {{
                const raw = (e.innerText || '').trim();
                const txt = raw.replace(/\\*/g, '').trim();
                if (txt !== target) continue;
                const r = e.getBoundingClientRect();
                if (r.width === 0 || r.height === 0 || r.height > 50) continue;
                let p = e.parentElement;
                for (let i = 0; i < 6 && p; i++, p = p.parentElement) {{
                    const inp = p.querySelector('input[placeholder="请输入"]');
                    if (inp) {{
                        const ri = inp.getBoundingClientRect();
                        if (ri.width > 0 && ri.height > 0 && ri.y > 60) {{
                            inp.scrollIntoView({{block: 'center', behavior: 'instant'}});
                            inp.focus();
                            return true;
                        }}
                    }}
                }}
            }}
            return false;
        }}""")
        if not ok:
            raise RuntimeError(f"未找到标签「{label}」对应的输入框")
        pg.wait_for_timeout(150)
        focused = fr.locator(":focus")
        if focused.count():
            focused.fill(str(value), timeout=3000)
        else:
            pg.keyboard.press("Control+a")
            pg.keyboard.press("Delete")
            pg.keyboard.type(str(value))
        pg.wait_for_timeout(150)
        filled.append({"label": label, "value": str(value)[:30]})
    return {"ok": True, "filled": filled}


def _select_category(fr, pg, category):
    """点击合同类别单选按钮。"""
    idx = CATEGORY_IDX.get(category, 0)
    # 找所有 class 含 attend-radio 的 <i> 标签（可见）
    radio_loc = fr.locator("i[class*='attend-radio']")
    total = radio_loc.count()
    visible = []
    for i in range(total):
        try:
            if radio_loc.nth(i).is_visible(timeout=300):
                visible.append(radio_loc.nth(i))
        except Exception:
            pass
    if not visible:
        # 备选：class 含 radio-uncheck
        radio_loc2 = fr.locator("[class*='radio-uncheck'],[class*='radio-check']")
        for i in range(radio_loc2.count()):
            try:
                if radio_loc2.nth(i).is_visible(timeout=300):
                    visible.append(radio_loc2.nth(i))
            except Exception:
                pass
    if not visible:
        raise RuntimeError("未找到合同类别 radio 按钮")
    if idx >= len(visible):
        raise RuntimeError(f"radio 索引 {idx} 越界，共 {len(visible)} 个")
    visible[idx].click(timeout=3000)
    pg.wait_for_timeout(300)
    return {"ok": True, "idx": idx, "total": len(visible)}


def _fill_officer(fr, pg, officer):
    """填写经办人：展开部门树 → 点 selectPersonBtn → 确定。"""
    officer_inp = fr.locator('input[placeholder=""]').first
    officer_inp.click(timeout=5000)
    pg.wait_for_timeout(1500)

    # 等弹框
    pg.locator('input[placeholder="输入查找的姓名"]').wait_for(state='visible', timeout=8000)
    pg.wait_for_timeout(500)

    def _click_select_btn(name):
        """在弹框内（y>140, x<1060）找到姓名行，点击同行的 selectPersonBtn。"""
        pos = pg.evaluate(f"""() => {{
            const name = {repr(name)};
            // 找弹框内的姓名元素（排除导航栏 y<140 和右侧已选面板 x>1060）
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
            // 找同行的 button.selectPersonBtn
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
        """点击弹框内下一个未展开的 iconCaret，返回是否点到。"""
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

    # 先展开一次（"我的"tab默认会有一个可展开的部门）
    _expand_next_caret()
    pg.wait_for_timeout(1500)

    # 直接找
    found = _click_select_btn(officer)

    if not found:
        # 继续展开更多 caret，每展开一次检查一次
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

    # 点「确定」
    pg.locator('button:has-text("确定")').last.click(timeout=5000)
    pg.wait_for_timeout(1000)

    filled_val = officer_inp.input_value(timeout=3000)
    return {"ok": True, "filled": filled_val}


def _close_upload_dialog(pg):
    """点击上传对话框里的确认按钮，等待 ui-widget-overlay 消失。"""
    for btn_text in ["确定", "上传", "提交", "保存", "OK"]:
        try:
            btn = pg.locator(f".ui-dialog button:has-text('{btn_text}')").first
            if btn.count() and btn.is_visible(timeout=1000):
                btn.click(timeout=3000)
                break
        except Exception:
            pass
    # 等待遮罩消失（最多 8 秒）
    try:
        pg.locator("div.ui-widget-overlay").wait_for(state="hidden", timeout=8000)
    except Exception:
        pass
    pg.wait_for_timeout(500)


def _upload_one(fr, pg, file_path, display_name):
    """上传单个附件。display_name 是显示给 rd-web 的文件名（用原始文件名）。"""
    import mimetypes as _mt

    if not os.path.exists(file_path):
        raise RuntimeError(f"附件文件不存在: {file_path}")

    # 点「添加附件」
    add_btn = fr.locator("[class*='item-customer-add']")
    if not add_btn.count() or not add_btn.first.is_visible(timeout=2000):
        add_btn = fr.get_by_text("添加附件").first
    add_btn.click(timeout=5000)
    pg.wait_for_timeout(2000)

    # 找「上传附件」按钮（先在主页面，再在 iframe 里）
    upload_btn = pg.locator("button.popshowfileuploadBtn")
    if not upload_btn.count() or not upload_btn.is_visible(timeout=4000):
        upload_btn = fr.locator("button.popshowfileuploadBtn")
        if not upload_btn.count() or not upload_btn.is_visible(timeout=4000):
            pg.screenshot(path="/tmp/upload_debug.png")
            raise RuntimeError(
                f"上传「{display_name}」时未找到「上传附件」按钮，"
                "已截图到 /tmp/upload_debug.png"
            )

    # 用 FilePayload 上传（保留原始文件名，而非 UUID）
    mime = _mt.guess_type(display_name)[0] or "application/octet-stream"
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    with pg.expect_file_chooser(timeout=6000) as fc_info:
        upload_btn.click(timeout=3000)
    fc_info.value.set_files([{"name": display_name, "mimeType": mime, "buffer": file_bytes}])

    # 等文件名出现在对话框（最多 20 秒）
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

    # 等 overlay 消失
    try:
        pg.locator("div.ui-widget-overlay").wait_for(state="hidden", timeout=8000)
    except Exception:
        pass
    pg.wait_for_timeout(800)


def _upload_attachments(fr, pg, attachments):
    """逐个上传附件列表。attachments = [{"path": str, "name": str}, ...]"""
    if not attachments:
        raise RuntimeError("未提供附件，rd-web 合同审签单要求必须上传附件")
    for item in attachments:
        _upload_one(fr, pg, item["path"], item["name"])
    return {"ok": True, "count": len(attachments)}


def _submit(fr, pg):
    """点「提交」并等待流水号。"""
    # 找最靠下的「提交」按钮
    submit_btns = fr.locator("button,a,[role=button]").all()
    target = None
    max_y = -1
    for btn in submit_btns:
        try:
            if not btn.is_visible(timeout=200):
                continue
            txt = (btn.inner_text() or "").strip()
            if txt != "提交":
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

    ERROR_KWS = ["必填", "不能为空", "请填写", "请上传", "不可为空",
                 "请选择", "校验失败", "提交失败"]

    def _get_fr_text():
        try:
            return fr.evaluate("()=>document.body.innerText")
        except Exception:
            return ""

    def _get_pg_text():
        try:
            return pg.evaluate("()=>document.body.innerText")
        except Exception:
            return ""

    # 先等表单关闭（最多 10 秒）：表单关闭后 innerText 不再包含「存草稿」
    form_closed = False
    for _ in range(10):
        pg.wait_for_timeout(1000)
        fr_text = _get_fr_text()
        if "存草稿" not in fr_text:
            form_closed = True
            break
        # 检查校验错误（表单仍开着时检查）
        for kw in ERROR_KWS:
            if kw in fr_text:
                lines = [l.strip() for l in fr_text.split("\n") if kw in l and l.strip()]
                return {"ok": False, "msg": f"表单校验失败: {lines[0][:80] if lines else kw}"}

    if not form_closed:
        pg.screenshot(path="/tmp/submit_timeout.png")
        return {"ok": False, "msg": "点提交后表单未关闭，可能存在校验错误",
                "page_text": _get_fr_text()[:400]}

    # 表单关闭 → 回到列表，切「我发起的」标签找流水号
    pg.wait_for_timeout(1000)
    try:
        tab = fr.get_by_text("我发起的", exact=True).first
        if tab.is_visible(timeout=3000):
            tab.click(timeout=3000)
            pg.wait_for_timeout(3000)
    except Exception:
        pass

    # 在列表里找流水号（格式：13位，20开头，如 2026062811498）
    # 排除日期（2026-xx-xx）、电话（8位）等干扰项
    for _ in range(8):
        fr_text = _get_fr_text()
        # 优先匹配 13 位纯数字（rd-web 流水号格式）
        for m in re.finditer(r"\b(\d{13})\b", fr_text):
            num = m.group(1)
            if num.startswith("20") and not re.search(r"\d{13}", num[4:8] + "-"):
                return {"ok": True, "serial_no": num}
        # 次优：10-15 位且不是电话号段
        m = re.search(r"\b(20\d{9,13})\b", fr_text)
        if m:
            return {"ok": True, "serial_no": m.group(1)}
        pg.wait_for_timeout(1000)

    # 截图留存，返回成功（表单已关闭 = 提交成功）
    try:
        pg.screenshot(path="/tmp/submit_timeout.png")
        snippet = _get_fr_text()[:400]
    except Exception:
        snippet = ""
    return {
        "ok": True,
        "serial_no": "",
        "msg": "表单已提交（流水号待从列表获取）",
        "page_text": snippet,
    }


# ── 主入口 ───────────────────────────────────────────────────────────────

def submit_contract(
    data: dict,
    file_path: str   = "",         # 兼容旧调用（代理协议用），单文件路径
    attachments: list = None,      # 优先：[{"path": str, "name": str}, ...]
    loginuser: str   = "13029144451",
    password: str    = "whywhy123",
) -> dict:
    """
    提交合同审签单。

    data 字段：
        合同名称 / 合同编码 / 项目名称及包号 / 归口管理科室 / 合同金额
        合同甲方 / 甲方法定代表人 / 甲方联系电话 / 甲方地址
        合同乙方 / 乙方法定代表人 / 乙方联系电话 / 乙方地址
        合同类别（采购部合同 / 其他合同 / 其他合同（已授权的简化流程））
        经办人

    file_path：合同文件本地绝对路径（空则跳过附件上传）

    返回：{"ok": bool, "serial_no": str, "msg": str, "detail": dict}
    """
    from playwright.sync_api import sync_playwright

    field_values = [data.get(f, "") for f in TEXT_FIELDS]
    category     = data.get("合同类别", "采购部合同")
    officer      = data.get("经办人", "")
    detail       = {}

    # 统一成 attachments 列表
    if not attachments and file_path:
        attachments = [{"path": file_path, "name": os.path.basename(file_path)}]

    state_path = _state_path(loginuser)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome",
            headless=True,
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
            # 1. 登录（session 有效时跳过）
            _login_if_needed(pg, ctx, loginuser, password, state_path)

            # 2. 导航到合同审签单
            fr = _nav_to_contract(pg)

            # 3. 打开新建表单
            _open_form(fr, pg)
            pg.wait_for_timeout(1000)

            # 4. 填写13个文本字段
            fill = _fill_text_fields(fr, pg, field_values)
            detail["fill"] = fill
            pg.wait_for_timeout(300)

            # 5. 选择合同类别
            cat = _select_category(fr, pg, category)
            detail["category"] = cat
            pg.wait_for_timeout(300)

            # 6. 上传附件（支持多个）
            upload = _upload_attachments(fr, pg, attachments)
            detail["upload"] = upload
            pg.wait_for_timeout(1000)

            # 7. 填写经办人
            if officer:
                ofc = _fill_officer(fr, pg, officer)
                detail["officer"] = ofc
                pg.wait_for_timeout(300)

            # 8. 提交
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
