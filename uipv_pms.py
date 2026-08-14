# -*- coding: utf-8 -*-
"""
PMS 文件预览侧栏验收。跑在测试实例（1574 / pms.test.db）上，正式服 1573 不碰。

用法：
    PV_PW=xxx ~/opms/venv/bin/python uipv_pms.py

为什么盯得这么紧：这个面板被 18 处地方调用，其中好几处是在 antd 弹窗**里面**
打开的，层级和让位都容易出错；而拖宽度那段在 OPMS 上真出过故障——
抬手的事件被面板里的 iframe 吃掉，松了手还在拖，只能刷页面。
所以下面**故意把鼠标抬在 iframe 上**，并且把「抬手点确实压在 iframe 上」
本身也写成一条断言：不这样，这条测试会悄悄变成白测（这个坑踩过一次）。
"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PV_BASE", "http://127.0.0.1:1574")
PW = os.environ["PV_PW"]
PROJECT = "测试1号项目"

ok = fail = 0
errs = []


def t(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS %s" % name)
    else:
        fail += 1
        print("  FAIL %s%s" % (name, ("  ← " + str(detail)) if detail else ""))


def pad(pg, sel):
    """量某个元素的右内边距——面板给主区让出来的那一条。"""
    return pg.evaluate(
        "s => { const e = document.querySelector(s);"
        " return e ? parseInt(getComputedStyle(e).paddingRight, 10) || 0 : -1 }", sel)


def run(pg):
    # ── 走「项目分发」这一屏 ──
    # 特意选它：附件列表在右侧抽屉里，文件在面板里，两个抢同一条地方。
    # 这是最容易出层级/让位问题的组合，也正是「边看边办」最典型的场景。
    pg.goto(BASE + "/project-distribution", wait_until="networkidle")
    # 等那个按钮真的出现，别用固定 sleep 等——这台机器同时在跑 OCR，
    # 负载一上去列表就渲染得慢，固定等法会时通时不通（已经红过一次）。
    pg.wait_for_selector('button:has-text("附件(")', timeout=40000)
    att = pg.locator('button:has-text("附件(")')
    t("分发列表里有带附件的记录", att.count() > 0, "%d 条" % att.count())

    # 挑一条附件数最多的，好验翻页
    best, bestn = 0, 0
    for k in range(min(att.count(), 12)):
        txt = att.nth(k).inner_text()
        n = int("".join(ch for ch in txt if ch.isdigit()) or 0)
        if n > bestn:
            best, bestn = k, n
    att.nth(best).click()
    pg.wait_for_selector(".ant-drawer-open", timeout=10000)
    pg.wait_for_timeout(1200)

    masks_before = pg.locator(".ant-modal-mask").count()
    pv_btn = pg.locator('.ant-drawer button:has-text("预览")')
    t("抽屉里有可预览的附件", pv_btn.count() > 0, "%d 个" % pv_btn.count())
    nfiles = pv_btn.count()
    pv_btn.first.click()
    pg.wait_for_selector(".pms-pv", timeout=20000)
    pg.wait_for_timeout(1500)

    # ── 侧栏该有的样子 ──
    t("预览是侧栏，不是弹窗", pg.locator(".pms-pv").count() == 1)
    t("预览没有再加一层遮罩（主区照样点得着）",
      pg.locator(".ant-modal-mask").count() == masks_before,
      "开面板前 %d，开面板后 %d" % (masks_before, pg.locator(".ant-modal-mask").count()))

    box = pg.locator(".pms-pv").bounding_box()
    w = box["width"]
    t("主区让出了正好一条面板的宽度", abs(pad(pg, "#root") - w) <= 1,
      "#root padding-right=%s，面板宽 %s" % (pad(pg, "#root"), w))

    # 抽屉必须挪到面板左边，不能被压在底下——否则列表点不着，翻页全靠面板
    dw = pg.locator(".ant-drawer-content-wrapper").bounding_box()
    t("右侧抽屉挪到了面板左边（列表和文件并排，不互相压）",
      dw and dw["x"] + dw["width"] <= box["x"] + 2,
      "抽屉右缘 %.0f，面板左缘 %.0f" % (dw["x"] + dw["width"] if dw else -1, box["x"]))

    # 面板压在抽屉之上：拿面板中心那一点去问「这里最上面是谁」
    top_is_pv = pg.evaluate(
        "p => { const e = document.elementFromPoint(p.x, p.y);"
        " return !!(e && e.closest('.pms-pv')) }",
        {"x": box["x"] + box["width"] / 2, "y": box["y"] + 60})
    t("面板盖在抽屉上面（不是被抽屉挡住）", top_is_pv)

    # 主区真的还能点：面板开着，去问主区某一点是不是可点的真元素
    main_hit = pg.evaluate(
        "p => { const e = document.elementFromPoint(p.x, p.y);"
        " return e ? (e.closest('.pms-pv') ? 'PANEL' : e.tagName) : 'NONE' }",
        {"x": 300, "y": 300})
    t("面板开着的时候主区不是被盖住的（没有遮罩层）",
      main_hit not in ("PANEL", "NONE"), main_hit)

    # ── 翻页 ──
    if nfiles > 1:
        head = pg.locator(".pms-pv-head").inner_text()
        t("面板上有第几件/共几件", "/" in head and "1/" in head, head)
        name1 = pg.locator(".pms-pv-name").inner_text()
        pg.locator('.pms-pv-head button').nth(1).click()      # 下一件
        pg.wait_for_timeout(1200)
        name2 = pg.locator(".pms-pv-name").inner_text()
        t("点「下一件」真的换了文件", name1 != name2, "%s → %s" % (name1, name2))
        t("翻页后计数跟着走", "2/" in pg.locator(".pms-pv-head").inner_text(),
          pg.locator(".pms-pv-head").inner_text())
        pg.locator('.pms-pv-head button').nth(0).click()      # 回上一件
        pg.wait_for_timeout(1200)
        t("点「上一件」能翻回去",
          pg.locator(".pms-pv-name").inner_text() == name1,
          pg.locator(".pms-pv-name").inner_text())
    else:
        t("翻页（这批只有一件，跳过）", True, "只有 1 件")

    # ── 拖宽度：松手就得真的停 ──
    t("拖动测试的前提：面板里确实是 iframe（会抢鼠标事件的那种）",
      pg.locator(".pms-pv-body iframe").count() == 1,
      "iframe %d 个" % pg.locator(".pms-pv-body iframe").count())
    grip = pg.locator(".pms-pv-grip").bounding_box()
    w0 = pg.locator(".pms-pv").bounding_box()["width"]
    mid = grip["y"] + 300
    pg.mouse.move(grip["x"] + 3, mid)
    pg.mouse.down()
    pg.mouse.move(grip["x"] - 160, mid, steps=8)          # 往左＝加宽
    pg.wait_for_timeout(300)
    w1 = pg.locator(".pms-pv").bounding_box()["width"]
    t("拖把手能把面板拉宽", w1 > w0 + 80, "%d → %d" % (w0, w1))
    t("拖动期间主区的让位跟着变（不会被面板压住）",
      abs(pad(pg, "#root") - w1) <= 1,
      "padding=%s 宽=%s" % (pad(pg, "#root"), w1))

    # 关键一步：抬手前先把鼠标挪到**面板里边**，也就是 iframe 正上方。
    # 抬手落在主区上是测不出这个 bug 的——外层照样收得到，白测。
    # 把手是跟着鼠标走的，所以直接算坐标会永远压在把手身上；这里利用
    # 最小宽度 360px 的限位：把鼠标推到更深处，宽度卡住不再跟，
    # 光标就真的落在 iframe 上了——这才是原来丢事件的位置。
    vw = pg.evaluate("window.innerWidth")
    inside = vw - 150
    pg.mouse.move(inside, mid, steps=6)
    pg.wait_for_timeout(300)
    ifr = pg.locator(".pms-pv-body iframe").bounding_box()
    t("抬手的位置确实压在 iframe 上（不然这条测试是白测的）",
      bool(ifr) and ifr["x"] <= inside <= ifr["x"] + ifr["width"]
      and ifr["y"] <= mid <= ifr["y"] + ifr["height"],
      "抬手点 x=%d y=%d，iframe %s" % (inside, mid, ifr))
    w1 = pg.locator(".pms-pv").bounding_box()["width"]
    pg.mouse.up()
    pg.wait_for_timeout(300)
    pg.mouse.move(grip["x"] - 500, mid + 90, steps=10)
    pg.wait_for_timeout(400)
    w2 = pg.locator(".pms-pv").bounding_box()["width"]
    t("松手之后鼠标乱动，宽度不再跟着变（就是 OPMS 上那个 bug）",
      abs(w2 - w1) < 6, "松手时 %d，乱动后 %d" % (w1, w2))
    t("松手后不再选不中字（userSelect 复位了）",
      pg.evaluate("document.body.style.userSelect") == "",
      pg.evaluate("document.body.style.userSelect"))
    t("拖动遮罩已经收掉，不挡点击", pg.locator(".pms-pv-shield.on").count() == 0)

    # 松手后界面还得能点。bug 期间整个界面等于失效，所以这条必须验。
    pg.locator(".pms-pv-head button").last.click()          # 关闭按钮
    pg.wait_for_timeout(600)
    t("松手后界面照样能点（不是被拖动状态粘住）",
      pg.locator(".pms-pv").count() == 0)
    t("面板关掉后主区把让位收回去了",
      pad(pg, "#root") == 0 and pg.locator("body.pms-pv-open").count() == 0,
      "padding=%s" % pad(pg, "#root"))
    dw2 = pg.locator(".ant-drawer-content-wrapper").bounding_box()
    t("面板关掉后抽屉挪回右边", dw2 and dw2["x"] + dw2["width"] >= vw - 2,
      "抽屉右缘 %.0f，屏宽 %d" % ((dw2["x"] + dw2["width"]) if dw2 else -1, vw))

    # ── 宽度记住了吗 ──
    saved = pg.evaluate("localStorage.getItem('pms-pv-w')")
    t("宽度存进了 localStorage", saved and int(saved) > 0, saved)
    pg.locator('.ant-drawer button:has-text("预览")').first.click()
    pg.wait_for_selector(".pms-pv", timeout=20000)
    pg.wait_for_timeout(1000)
    w3 = pg.locator(".pms-pv").bounding_box()["width"]
    t("重新打开还是上次那个宽度", abs(w3 - int(saved)) <= 1, "存 %s，现在 %s" % (saved, w3))

    # ── 右键别当拖动 ──
    grip = pg.locator(".pms-pv-grip").bounding_box()
    wa = pg.locator(".pms-pv").bounding_box()["width"]
    pg.mouse.move(grip["x"] + 3, grip["y"] + 300)
    pg.mouse.down(button="right")
    pg.mouse.move(grip["x"] - 220, grip["y"] + 300, steps=6)
    pg.wait_for_timeout(300)
    wb = pg.locator(".pms-pv").bounding_box()["width"]
    pg.mouse.up(button="right")
    t("右键按住拖，宽度不动（用户报过右键也跟着变）", abs(wb - wa) < 6,
      "%d → %d" % (wa, wb))

    # ── 自愈：漏了一次抬起也不能永远粘住 ──
    # 合成事件，模拟「切窗口回来时鼠标键其实已经松了」那种漏抬。
    grip = pg.locator(".pms-pv-grip").bounding_box()
    wc = pg.locator(".pms-pv").bounding_box()["width"]
    pg.evaluate(
        """g => {
          const el = document.querySelector('.pms-pv-grip');
          const mk = (type, x, buttons) => new PointerEvent(type, {
            bubbles: true, cancelable: true, pointerId: 7, button: 0,
            buttons, clientX: x, clientY: g.y + 300 });
          el.dispatchEvent(mk('pointerdown', g.x + 3, 1));
          el.dispatchEvent(mk('pointermove', g.x - 120, 0));   // 键已经松了
          el.dispatchEvent(mk('pointermove', g.x - 400, 0));   // 还动，但不该再改
        }""", grip)
    pg.wait_for_timeout(400)
    wd = pg.locator(".pms-pv").bounding_box()["width"]
    t("漏了一次抬起也能自愈：发现键松了就停手", abs(wd - wc) < 40,
      "%d → %d" % (wc, wd))

    # ── Esc 关闭 ──
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)
    t("Esc 能关掉面板（没有遮罩，键盘是随手关的通道）",
      pg.locator(".pms-pv").count() == 0)
    t("Esc 关掉后让位也收回", pad(pg, "#root") == 0, pad(pg, "#root"))


def run_plain(pg):
    """再验一个**没有抽屉/弹窗**的页面：询/议价函列表，预览直接从卡片上开。

    为什么要分开验：antd 的抽屉和弹窗都带焦点锁，会把焦点从面板的把手上抢回去
    （实测聚焦后 activeElement 变成 ant-drawer-close）。所以「把手聚焦＋方向键
    调宽度」这条只在普通页面上成立——而普通页面恰好是大多数调用点。
    上一段在抽屉页测这条会红，红的却不是功能，是 antd 的焦点锁，白耗。
    """
    # 上一段把宽度拖到过最小值并且记住了。带着它进下一段，等于让「上一段
    # 干了什么」决定这一段量到多少——出问题很难复现。这里先钉回一个已知宽度。
    pg.goto(BASE + "/inquiry", wait_until="domcontentloaded")
    pg.evaluate("() => localStorage.setItem('pms-pv-w', '620')")
    pg.goto(BASE + "/inquiry", wait_until="networkidle")
    pg.wait_for_selector('button:has-text("预览")', timeout=40000)
    btn = pg.locator('button:has-text("预览")')
    t("询价函列表上有预览入口", btn.count() > 0, "%d 个" % btn.count())
    btn.first.click()
    pg.wait_for_selector(".pms-pv", timeout=25000)
    pg.wait_for_timeout(2500)

    t("普通页面上也是侧栏", pg.locator(".pms-pv").count() == 1)
    t("这一屏没有抽屉/弹窗（所以焦点不会被抢走）",
      pg.locator(".ant-drawer-open").count() == 0
      and pg.locator(".ant-modal-mask").count() == 0)
    t("面板里真渲染出了东西（不是空白）",
      len(pg.locator(".pms-pv-body").inner_text().strip()) > 20
      or pg.locator(".pms-pv-body iframe, .pms-pv-body img").count() > 0,
      pg.locator(".pms-pv-body").inner_text()[:80])
    t("没有停在「加载中」或报错上",
      "加载失败" not in pg.locator(".pms-pv-body").inner_text()
      and "暂不支持" not in pg.locator(".pms-pv-body").inner_text(),
      pg.locator(".pms-pv-body").inner_text()[:80])

    # docx 按 A4 真实宽度铺（≈794px），面板窄的时候必须自动缩到放得下，
    # 不然右边一截被切掉、得横着拖才能看全——旧弹窗有 80% 屏宽所以从没露出来。
    if pg.locator(".pms-pv-body .docx-wrapper").count():
        ov = pg.evaluate("""() => { const e = document.querySelector('.pms-pv-body');
          return { sw: e.scrollWidth, cw: e.clientWidth,
                   zoom: getComputedStyle(e.firstElementChild).zoom } }""")
        t("docx 自动缩到面板宽度，不横向溢出",
          ov["sw"] <= ov["cw"] + 4, "scrollWidth=%s clientWidth=%s zoom=%s"
          % (ov["sw"], ov["cw"], ov["zoom"]))
        # 拖宽以后应该放回去，不能一直缩着
        pg.evaluate("() => document.querySelector('.pms-pv').style.width = '1100px'")
        pg.wait_for_timeout(700)
        z2 = pg.evaluate("() => getComputedStyle(document.querySelector('.pms-pv-body').firstElementChild).zoom")
        t("面板拉宽以后 docx 放回原尺寸（只缩不放大）",
          float(z2 or 1) >= float(ov["zoom"] or 1), "%s → %s" % (ov["zoom"], z2))
        pg.evaluate("() => document.querySelector('.pms-pv').style.width = ''")
        pg.wait_for_timeout(400)
    else:
        t("docx 自适应（这一件不是 docx，跳过）", True,
          pg.locator(".pms-pv-body").get_attribute("class") or "")

    # 方向键调宽度
    we = pg.locator(".pms-pv").bounding_box()["width"]
    pg.locator(".pms-pv-grip").focus()
    t("把手能拿到焦点（这一屏没有焦点锁）",
      pg.evaluate("()=>document.activeElement.className").find("pms-pv-grip") >= 0,
      pg.evaluate("()=>document.activeElement.className"))
    pg.keyboard.press("ArrowLeft")
    pg.wait_for_timeout(400)
    wf = pg.locator(".pms-pv").bounding_box()["width"]
    t("把手聚焦后方向键能调宽度", wf > we + 10, "%d → %d" % (we, wf))
    pg.keyboard.press("ArrowRight")
    pg.wait_for_timeout(400)
    t("方向键往回也能调", pg.locator(".pms-pv").bounding_box()["width"] < wf - 10)

    # 放宽 / 收窄
    wg = pg.locator(".pms-pv").bounding_box()["width"]
    pg.locator('.pms-pv-head button').nth(0).click()      # 这一屏没翻页，第0个就是放宽
    pg.wait_for_timeout(500)
    wh = pg.locator(".pms-pv").bounding_box()["width"]
    t("「放宽」一键铺开", wh > wg + 100, "%d → %d" % (wg, wh))
    pg.locator('.pms-pv-head button').nth(0).click()
    pg.wait_for_timeout(500)
    t("再点一次收回来", pg.locator(".pms-pv").bounding_box()["width"] < wh - 100)

    # 主区照样能用：面板开着的时候去点列表里的筛选，页面得有反应
    t("面板开着，主区的控件不是被盖住的",
      pg.evaluate("""() => { const e = document.elementFromPoint(320, 200);
        return !!(e && !e.closest('.pms-pv')) }"""))

    # ── 弹窗也得让位（机制级检查，不是端到端）──
    # 有好几处调用点是在 antd 弹窗**里面**开预览的（采购文件附件、公告附件、
    # 合同附件…），弹窗在 .ant-modal-wrap 那一层居中，不给它让位右半截就被压住。
    # 但这套系统的表单基本都用抽屉，当前账号能看到的数据里点不出一个真弹窗，
    # 所以这里退一步只验「那条 CSS 规则确实命中」：面板开着时插一个空的
    # .ant-modal-wrap，看它有没有拿到让位。**这条不能证明端到端好用**，
    # 只能证明规则没写错（比如选择器打错、被 antd 的样式盖掉）。
    w_before = pg.locator(".pms-pv").bounding_box()["width"]
    got = pg.evaluate("""() => {
      const d = document.createElement('div');
      d.className = 'ant-modal-wrap';
      document.body.appendChild(d);
      const px = parseInt(getComputedStyle(d).paddingRight, 10) || 0;
      d.remove();
      return px }""")
    t("弹窗那一层也能拿到让位（规则命中，非端到端）",
      abs(got - w_before) <= 1, "量到 %s，面板宽 %s" % (got, w_before))

    # 没有别的层时，Esc 一下就关
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(700)
    t("普通页面上 Esc 一下就关（不用按两次）",
      pg.locator(".pms-pv").count() == 0)
    t("Esc 关掉后让位也收回", pad(pg, "#root") == 0, pad(pg, "#root"))

    # ── 和别的层叠在一起时，一次 Esc 只关一层 ──
    # 面板在最上面，Esc 就该先关面板；要是一下把底下正在填的表单也关了，
    # 填了半天的东西就没了。这条是真出现过的：两边都收 Esc，一按全关。
    pg.locator('button:has-text("预览")').first.click()
    pg.wait_for_selector(".pms-pv", timeout=25000)
    pg.wait_for_timeout(1200)
    pg.locator('button:has-text("新建函件")').first.click()
    pg.wait_for_selector(".ant-drawer-open", timeout=10000)
    pg.wait_for_timeout(900)
    t("面板开着也能点主区的按钮（表单真弹出来了）",
      pg.locator(".ant-drawer-open").count() > 0)
    dwb = pg.locator(".ant-drawer-content-wrapper").last.bounding_box()
    pvb = pg.locator(".pms-pv").bounding_box()
    t("这个表单抽屉也挪到了面板左边",
      dwb and dwb["x"] + dwb["width"] <= pvb["x"] + 2,
      "抽屉右缘 %.0f，面板左缘 %.0f" % ((dwb["x"] + dwb["width"]) if dwb else -1, pvb["x"]))

    pg.keyboard.press("Escape")
    pg.wait_for_timeout(900)
    t("Esc 先关预览，不连带把正在填的表单关掉",
      pg.locator(".pms-pv").count() == 0
      and pg.locator(".ant-drawer-open").count() > 0,
      "面板 %d，抽屉 %d" % (pg.locator(".pms-pv").count(),
                          pg.locator(".ant-drawer-open").count()))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(900)
    t("再按一次才轮到表单抽屉（一次 Esc 只关一层）",
      pg.locator(".ant-drawer-open").count() == 0)


def run_images(pg):
    """图片 + 多件翻页：项目评审的资料里是「一份评审情况 PDF ＋ 几张签字照」。

    这一段专门盯两件事：
      ① 图片现在**贴在面板里**看，不再弹一个全屏遮罩——弹遮罩就等于把
         刚去掉的那层挡视线的东西又请回来了，边看边办就没了。
      ② 在面板上翻页时，渲染方式要跟着文件类型换（图片 ↔ PDF）。
         这条最容易漏：状态留在上一件身上，翻过去就白屏或者还显示旧的。
    """
    pg.goto(BASE + "/project-review", wait_until="domcontentloaded")
    pg.evaluate("() => localStorage.setItem('pms-pv-w', '620')")
    pg.goto(BASE + "/project-review", wait_until="networkidle")
    pg.wait_for_selector('button:has-text("上传/查看评审结果")', timeout=40000)
    pg.locator(".ant-tabs-tab", has_text="已审核").click()
    pg.wait_for_timeout(2500)
    btn = pg.locator('button:has-text("上传/查看评审结果")')
    opened = False
    for i in range(btn.count()):
        anc = btn.nth(i).locator("xpath=ancestor::*[self::div][3]")
        try:
            if "心脏脉冲" in anc.inner_text():
                btn.nth(i).click()
                opened = True
                break
        except Exception:                       # noqa: BLE001  卡片结构不一，跳过
            continue
    t("找到那个带图片附件的评审项目", opened)
    if not opened:
        return
    pg.wait_for_selector(".ant-drawer-open", timeout=10000)
    pg.wait_for_timeout(1500)

    eyes = pg.locator(".ant-drawer .anticon-eye")
    t("评审资料里有多件可预览", eyes.count() >= 4, "%d 件" % eyes.count())

    # 逐个点，找出第一张图片
    shot = None
    for i in range(eyes.count()):
        eyes.nth(i).click()
        pg.wait_for_selector(".pms-pv", timeout=20000)
        pg.wait_for_timeout(1200)
        nm = pg.locator(".pms-pv-name").inner_text()
        if nm.lower().endswith((".jpg", ".jpeg", ".png")):
            shot = nm
            break
        pg.locator(".pms-pv-head button").last.click()
        pg.wait_for_timeout(500)
    t("点开了一张图片", bool(shot), shot)
    if not shot:
        return

    t("图片是贴在面板里看的，不是又弹一层全屏遮罩",
      pg.locator(".pms-pv-body img").count() == 1
      and pg.locator(".ant-image-preview-wrap").count() == 0,
      "img=%d 全屏预览=%d" % (pg.locator(".pms-pv-body img").count(),
                            pg.locator(".ant-image-preview-wrap").count()))
    ov = pg.evaluate("""() => { const e = document.querySelector('.pms-pv-body');
      return { sw: e.scrollWidth, cw: e.clientWidth } }""")
    t("图片默认缩到面板宽度内（不用横着拖）", ov["sw"] <= ov["cw"] + 4,
      "scrollWidth=%s clientWidth=%s" % (ov["sw"], ov["cw"]))
    t("图片真的加载出来了（不是碎图）",
      pg.evaluate("""() => { const i = document.querySelector('.pms-pv-body img');
        return !!(i && i.complete && i.naturalWidth > 0) }"""))

    # 点一下切原始大小——证件、签字要凑近看
    pg.locator(".pms-pv-body img").click()
    pg.wait_for_timeout(500)
    t("点一下切到原始大小（能凑近看签字/印章）",
      pg.evaluate("""() => { const i = document.querySelector('.pms-pv-body img');
        return getComputedStyle(i).maxWidth === 'none' }"""))
    pg.locator(".pms-pv-body img").click()
    pg.wait_for_timeout(500)

    # 翻页：从图片翻到 PDF，渲染方式必须跟着换
    n = int(pg.locator(".pms-pv-head").inner_text().split("/")[1].split()[0])
    t("面板上显示了共几件", n >= 4, "共 %d 件" % n)
    switched = False
    for _ in range(n):
        pg.locator('.pms-pv-head button').nth(1).click()     # 下一件
        pg.wait_for_timeout(1500)
        nm = pg.locator(".pms-pv-name").inner_text()
        if nm.lower().endswith(".pdf"):
            switched = pg.locator(".pms-pv-body iframe").count() == 1 \
                and pg.locator(".pms-pv-body img").count() == 0
            t("从图片翻到 PDF，渲染方式跟着换了（没留在上一件上）",
              switched, "翻到 %s，iframe=%d img=%d"
              % (nm, pg.locator(".pms-pv-body iframe").count(),
                 pg.locator(".pms-pv-body img").count()))
            break
    if not switched:
        t("从图片翻到 PDF，渲染方式跟着换了（没留在上一件上）", False, "没翻到 PDF")

    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)
    t("看完关掉，让位收回", pad(pg, "#root") == 0, pad(pg, "#root"))


def main():
    with sync_playwright() as p:
        b = p.chromium.launch()
        c = b.new_context(viewport={"width": 1600, "height": 900})
        pg = c.new_page()
        pg.on("pageerror", lambda e: errs.append("pageerror: %s" % e))
        pg.on("console", lambda m: errs.append("console.error: %s" % m.text)
              if m.type == "error" else None)
        r = pg.request.post(BASE + "/api/auth/login",
                            data={"username": "admin", "password": PW})
        assert r.ok, "登录失败：%s %s" % (r.status, r.text())
        try:
            run(pg)
            run_plain(pg)
            run_images(pg)
        finally:
            b.close()
    # 页面报错单独算——功能「看着对」但控制台在刷红，不算过
    for e in errs:
        print("  ERR  %s" % e)
    print("\n结果：%d 通过 / %d 失败 / %d 页面报错" % (ok, fail, len(errs)))
    sys.exit(1 if (fail or errs) else 0)


if __name__ == "__main__":
    main()
