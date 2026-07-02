"""
探索 rd-web「采购项目审批/备案」表单结构。
运行：cd /home/huangxb/pms/backend && ../venv/bin/python ../explore_approval_form.py
截图保存到 /tmp/approval_*.png
"""
import os, time, json, sys
sys.path.insert(0, "/home/huangxb/pms/backend")

from playwright.sync_api import sync_playwright

LOGIN_URL  = "https://rd-web.mobimedical.cn/"
STATE_PATH = os.path.expanduser("~/pms/.rdweb_session.json")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            channel="chrome", headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx_kwargs = {
            "user_agent": UA,
            "viewport": {"width": 1920, "height": 1080},
        }
        if os.path.exists(STATE_PATH):
            ctx_kwargs["storage_state"] = STATE_PATH
            print("复用已有 session")
        ctx = browser.new_context(**ctx_kwargs)
        pg  = ctx.new_page()

        pg.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
        pg.wait_for_timeout(4000)

        # 登录（session 失效时）
        if pg.locator("#loginBtn").count() and pg.locator("#loginBtn").is_visible():
            print("需要登录")
            pg.fill("#loginUser", "13029144451")
            pg.fill("#password",  "whywhy123")
            pg.click("#loginBtn")
            pg.wait_for_timeout(5000)
            ctx.storage_state(path=STATE_PATH)
        else:
            print("session 有效，已登录")

        pg.screenshot(path="/tmp/approval_01_home.png")
        print("截图 01: 主页")

        # 枚举左侧所有菜单文字
        all_menu = pg.evaluate("""() => {
            return [...document.querySelectorAll('*')]
                .filter(e => {
                    const t = (e.innerText||'').trim();
                    const r = e.getBoundingClientRect();
                    return t.length > 1 && t.length < 30 && r.width > 0 && r.height > 0
                           && r.x < 200;  // 左侧导航区
                })
                .map(e => (e.innerText||'').trim())
                .filter((v, i, a) => a.indexOf(v) === i);
        }""")
        print("左侧菜单文本:", json.dumps(all_menu, ensure_ascii=False))

        # 尝试点击采购项目审批相关菜单
        keywords = ["采购项目审批", "项目资料备案", "采购备案", "项目审批", "备案"]
        clicked_name = None
        for kw in keywords:
            result = pg.evaluate(f"""() => {{
                const el = [...document.querySelectorAll('*')].find(e => {{
                    const t = (e.innerText||'').trim();
                    const r = e.getBoundingClientRect();
                    return t === {repr(kw)} && r.width > 0 && r.height > 0;
                }});
                if (el) {{ el.click(); return true; }}
                return false;
            }}""")
            if result:
                clicked_name = kw
                print(f"点击菜单: {kw}")
                pg.wait_for_timeout(4000)
                break

        if not clicked_name:
            print("⚠️  未找到任何采购项目审批菜单，截图左侧导航")
            pg.screenshot(path="/tmp/approval_02_nav_fail.png")
            browser.close()
            return

        pg.screenshot(path="/tmp/approval_02_after_menu.png")
        print("截图 02: 点击菜单后")

        # 列出所有 iframe URL
        frames = pg.frames
        print(f"共 {len(frames)} 个 frame：")
        for i, fr in enumerate(frames):
            url = fr.url or ""
            try:
                text_preview = fr.evaluate("()=>document.body.innerText")[:100].replace("\n"," ")
            except Exception:
                text_preview = "(无法读取)"
            print(f"  [{i}] {url[:80]}  |  {text_preview}")

        # 找包含「发起」和「项目名称」或「资料名称」的 frame
        target_fr = None
        for fr in frames:
            try:
                t = fr.evaluate("()=>document.body.innerText")
                if ("发起" in t or "项目名称" in t) and fr.url:
                    target_fr = fr
                    print(f"目标 frame URL: {fr.url}")
                    break
            except Exception:
                pass

        if target_fr is None:
            print("未找到目标 frame，用主页面继续")
            target_fr = pg

        # 点发起，打开新建表单
        try:
            clicked_qi = target_fr.evaluate("""() => {
                const el = [...document.querySelectorAll('*')].find(e =>
                    e.children.length <= 2 && (e.innerText||'').trim() === '发起'
                    && e.getBoundingClientRect().width > 0);
                if (el) { el.click(); return true; }
                return false;
            }""")
            print(f"点「发起」: {clicked_qi}")
            pg.wait_for_timeout(3000)
        except Exception as e:
            print(f"点发起失败: {e}")

        pg.screenshot(path="/tmp/approval_03_form.png")
        print("截图 03: 表单（发起后）")

        # 读取表单内容
        try:
            form_text = target_fr.evaluate("()=>document.body.innerText")
            print("表单文本（前600字）:")
            print(form_text[:600])
        except Exception as e:
            print(f"读取表单文本失败: {e}")

        # 枚举所有 input 和 select
        try:
            inputs = target_fr.evaluate("""() => {
                return [...document.querySelectorAll('input,select,textarea')]
                    .filter(e => e.getBoundingClientRect().width > 0)
                    .map(e => ({
                        tag: e.tagName,
                        type: e.type || '',
                        placeholder: e.placeholder || '',
                        name: e.name || '',
                        id: e.id || '',
                        options: e.tagName === 'SELECT'
                            ? [...e.options].map(o => o.text)
                            : [],
                    }));
            }""")
            print("表单元素:")
            print(json.dumps(inputs, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"枚举元素失败: {e}")

        ctx.storage_state(path=STATE_PATH)
        browser.close()
        print("完成")

if __name__ == "__main__":
    run()
