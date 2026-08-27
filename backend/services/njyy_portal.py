# -*- coding: utf-8 -*-
"""医院官网（www.njyy.com.cn）挂网驱动。

后台是 ThinkPHP 老 CMS，路由形如 /managernjyy-控制器-动作-参数-值.html。
人工流程（见「将采购公告发布到医院官网.docx」）是：sjkfb 填报 → sjksh 审核 →
点生成列表页。这里把那套流程原样自动化，接口对应关系：

  新增        POST /managernjyy-News-add-sort-34.html   （title / addtime / content）
  附件上传    POST /UE/php/controller.php?action=uploadfile （字段 upfile，UEditor）
  查看列表    GET  /managernjyy-News-lists-sort-34.html
  审核开关    GET  /managernjyy-News-change-id-<id>-zd-isshow.html   （sjksh 才有）
  删除        GET  /managernjyy-News-del-id-<id>.html
  生成列表页  GET  /managernjyy-Config-makelists-id-34.html
  生成详情页  GET  /managernjyy-Config-makeinfo-sort-34.html
  公网地址    https://www.njyy.com.cn/News/info/id/<id>.html

两个坑：
① 登录要过 4 位扭曲验证码。验证码图池不大且会重复，所以按图片指纹缓存
   「指纹→验证码」，认过一次以后直接命中；没命中才走本机 PaddleOCR，
   识别错了就换一张重来（后台对错误验证码只是报错，不锁账号）。
② 登录态只要不点「安全退出」就一直有效，所以 PHPSESSID 落盘复用，
   下次直接带着走；被弹回登录页才重新登录。
"""
import concurrent.futures as cf
import datetime
import hashlib
import io
import json
import os
import random
import re
import threading

import requests

try:                                  # 图像预处理是可选的，没有就直接喂原图
    import cv2
    import numpy as np
    from PIL import Image
    _HAS_CV = True
except Exception:                     # pragma: no cover
    _HAS_CV = False

requests.packages.urllib3.disable_warnings()

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CFG_PATH = os.environ.get("PMS_NJYY_CFG", os.path.join(_ROOT, ".njyy_portal.json"))
SESS_PATH = os.path.join(_ROOT, ".njyy_session.json")
CAP_PATH = os.path.join(_ROOT, ".njyy_captcha.json")
OCR_URL = os.environ.get("PMS_OCR_URL", "http://127.0.0.1:8118/ocr_classic")

SORT_ID = 34                          # 招标采购信息栏目
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_lock = threading.Lock()              # 同一时刻只允许一路操作官网，别把会话搅乱


class PortalError(RuntimeError):
    pass


# ── 配置 / 缓存 ────────────────────────────────────────────────────
def load_cfg():
    if not os.path.exists(CFG_PATH):
        raise PortalError("没有找到官网配置 %s" % CFG_PATH)
    with io.open(CFG_PATH, encoding="utf-8") as f:
        return json.load(f)


def enabled():
    try:
        return bool(load_cfg().get("enabled", True))
    except Exception:
        return False


def _load_json(path, default):
    try:
        with io.open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, obj):
    tmp = path + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


# ── 验证码 ────────────────────────────────────────────────────────
def _variants(img):
    """原图 + 两种净化图。干扰椭圆比字符笔画细，开运算能抹掉。"""
    if not _HAS_CV:
        return [img]
    try:
        arr = np.array(Image.open(io.BytesIO(img)).convert("L"))
        _, bw = cv2.threshold(arr, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        op = cv2.morphologyEx(bw, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        return [
            cv2.imencode(".png", 255 - cv2.resize(cv2.medianBlur(op, 3), None, fx=4, fy=4))[1].tobytes(),
            cv2.imencode(".png", 255 - cv2.resize(bw, None, fx=4, fy=4,
                                                  interpolation=cv2.INTER_CUBIC))[1].tobytes(),
            img,
        ]
    except Exception:
        return [img]


def _ocr(img):
    try:
        r = requests.post(OCR_URL, files={"file": ("c.png", img, "image/png")}, timeout=60)
        md = (r.json() or {}).get("markdown", "")
    except Exception:
        return ""
    md = re.sub(r"<!--page:\d+-->", "", md)
    return re.sub(r"[^A-Za-z0-9]", "", md)


def _captcha_guesses(img):
    """先查指纹缓存，再退回 OCR；返回按可信度排的候选。"""
    fp = hashlib.sha1(img).hexdigest()
    cache = _load_json(CAP_PATH, {})
    out = []
    if cache.get(fp):
        out.append(cache[fp])
    for v in _variants(img):
        g = _ocr(v)
        if len(g) == 4 and g not in out:
            out.append(g)
    return fp, out


def _remember_captcha(fp, code):
    cache = _load_json(CAP_PATH, {})
    if cache.get(fp) != code:
        cache[fp] = code
        _save_json(CAP_PATH, cache)


# ── 会话 ──────────────────────────────────────────────────────────
def _new_session():
    s = requests.Session()
    s.verify = False
    s.headers["User-Agent"] = UA
    return s


def _logged_in(s, cfg):
    """拿一个必须登录才能看的页面探活：被退回登录页就是掉线了。"""
    try:
        r = s.get(cfg["base"] + "/managernjyy-Index-menuframe.html", timeout=20)
    except Exception:
        return False
    return r.status_code == 200 and "安全退出" in r.text


def _do_login(s, cfg, acc, tries=25):
    entry = cfg["base"] + cfg["admin_entry"]
    last = ""
    for _ in range(tries):
        s.cookies.clear()
        s.get(entry, timeout=30)
        img = s.get(cfg["base"] + cfg["captcha_path"].format(rand=random.random()),
                    timeout=30).content
        fp, guesses = _captcha_guesses(img)
        if not guesses:
            continue
        for code in guesses:
            r = s.post(entry, data={"action": "login", "username": acc["username"],
                                    "password": acc["password"], "yzm": code}, timeout=30)
            if "验证码错误" in r.text:
                last = "验证码错误"
                continue
            if "frameset" in r.text:
                _remember_captcha(fp, code)      # 认对了就记住这张图
                return True
            last = _err_of(r.text) or "登录被拒"
            return False                          # 账号密码不对，再试也没用
    raise PortalError("官网登录失败（连试 %d 次验证码）%s"
                      % (tries, ("：" + last) if last else ""))


def _session_for(role):
    """role: publisher(填报 sjkfb) / auditor(审核 sjksh)。复用落盘的 PHPSESSID。"""
    cfg = load_cfg()
    acc = cfg[role]
    store = _load_json(SESS_PATH, {})
    s = _new_session()
    saved = (store.get(role) or {}).get("cookie")
    if saved:
        s.cookies.set("PHPSESSID", saved, domain="www.njyy.com.cn")
        if _logged_in(s, cfg):
            return s, cfg
    s = _new_session()
    _do_login(s, cfg, acc)
    store[role] = {"cookie": s.cookies.get("PHPSESSID", ""),
                   "at": datetime.datetime.now().isoformat(timespec="seconds")}
    _save_json(SESS_PATH, store)
    return s, cfg


def _err_of(html):
    m = re.search(r'class="error">([^<]*)<', html or "")
    return (m.group(1).strip() if m else "")


def _check(html, what):
    if "出错啦" in (html or "") or _err_of(html):
        raise PortalError("%s失败：%s" % (what, _err_of(html) or "官网返回错误页"))


# ── 动作 ──────────────────────────────────────────────────────────
def upload_file(s, cfg, filename, blob):
    """走 UEditor 的附件上传口，返回官网上的相对路径。"""
    r = s.post(cfg["base"] + "/UE/php/controller.php?action=uploadfile",
               files={"upfile": (filename, blob, "application/octet-stream")}, timeout=180)
    try:
        data = json.loads(re.sub(r"^[^{]*", "", r.text))
    except Exception:
        raise PortalError("附件「%s」上传返回看不懂：%s" % (filename, r.text[:120]))
    if (data.get("state") or "") != "SUCCESS":
        raise PortalError("附件「%s」上传失败：%s" % (filename, data.get("state")))
    return data.get("url") or ""


def _gen_one(s, cfg, path):
    """触发生成一个静态页。必须带 AJAX 头——不带就是 404，
    官网前台按 X-Requested-With 区分「生成」和「浏览」，返回 {"rs":1} 才算成。"""
    try:
        r = s.get(cfg["base"] + path, timeout=120,
                  headers={"X-Requested-With": "XMLHttpRequest"})
    except Exception:
        return False
    return r.status_code == 200 and '"rs"' in r.text


def gen_detail(s, cfg, news_id):
    """只生成这一条的详情页。后台那个「生成详情页」是把全栏目 2900+ 条
    排队让浏览器一条条打，我们只需要自己这条。"""
    return _gen_one(s, cfg, "/News/info/id/%d" % int(news_id))


def gen_lists(s, cfg, workers=6):
    """重建栏目列表页。入口页返回 url_arr（149 个分页 URL），逐个触发；
    新增/删除一条会让所有分页往后错一位，所以必须整份重建。"""
    entry = s.get(cfg["base"] + "/managernjyy-Config-makelists-id-%d.html" % SORT_ID,
                  timeout=300).text
    m = re.search(r"var url_arr=(\[.*?\]);", entry, re.S)
    if not m:
        raise PortalError("生成列表页：没解析出待生成的 URL 列表")
    urls = json.loads(m.group(1))
    ok = 0
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(lambda u: _gen_one(s, cfg, u), urls):
            ok += 1 if r else 0
    if ok == 0:
        raise PortalError("生成列表页：%d 个页面一个都没生成成功" % len(urls))
    return ok, len(urls)


def _find_id_by_title(s, cfg, title):
    """在栏目列表首页按标题找回刚建的记录 id（新记录排最前）。"""
    html = s.get(cfg["base"] + "/managernjyy-News-lists-sort-%d.html" % SORT_ID, timeout=30).text
    for tr in re.findall(r"<tr.*?</tr>", html, re.S):
        if title in tr:
            ids = re.findall(r'name="theId" value="(\d+)"', tr)
            if ids:
                return int(ids[0])
    return None


def publish(title, content_html, attachments=None, audit=True, regenerate=True):
    """把一条公告挂到官网。返回 {news_id, url, steps, verified}。

    attachments: [(文件名, 字节)]，会先传到官网再以链接附在正文末尾——
    人工操作时点回形针插进正文，效果一样。
    """
    attachments = attachments or []
    with _lock:
        steps = []
        s, cfg = _session_for("publisher")
        steps.append("sjkfb 已登录")

        links = []
        for name, blob in attachments:
            url = upload_file(s, cfg, name, blob)
            links.append((name, url))
            steps.append("附件已传：%s → %s" % (name, url))

        body = content_html
        if links:
            body += '<p style="margin-top:16px">附件：</p>' + "".join(
                '<p><a href="%s">%s</a></p>' % (u, n) for n, u in links)

        r = s.post(cfg["base"] + "/managernjyy-News-add-sort-%d.html" % SORT_ID,
                   data={"title": title,
                         "addtime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                         "content": body}, timeout=180)
        _check(r.text, "新增信息")
        steps.append("已在「招标采购信息」新增")

        news_id = _find_id_by_title(s, cfg, title)
        if not news_id:
            raise PortalError("新增后在列表里找不到这条记录，请到官网后台确认")
        steps.append("记录 id=%d" % news_id)

        if audit:
            a, cfg = _session_for("auditor")
            r = a.get(cfg["base"] + "/managernjyy-News-change-id-%d-zd-isshow.html" % news_id,
                      timeout=60)
            _check(r.text, "审核")
            steps.append("sjksh 已审核")
            if regenerate:
                if not gen_detail(a, cfg, news_id):
                    raise PortalError("详情页生成失败，公众看不到这条公告")
                steps.append("已生成详情页")
                ok, total = gen_lists(a, cfg)
                steps.append("已重建列表页 %d/%d" % (ok, total))

        url = "%s/News/info/id/%d.html" % (cfg["base"], news_id)
        return {"news_id": news_id, "url": url, "steps": steps,
                "verified": verify(url, title) if (audit and regenerate) else False}


def verify(url, title_part=""):
    """复核：公网详情页能打开、标题对得上，才算真挂上了。

    坑：后台删掉记录后，那个静态页还在，但内容被换成官网自己的
    「信息不存在！」弹窗页，HTTP 仍是 200——只看状态码会误判成还挂着。
    """
    try:
        r = requests.get(url, timeout=30, verify=False)
    except Exception:
        return False
    if r.status_code != 200:
        return False
    txt = r.content.decode("utf-8", "ignore")
    if "信息不存在" in txt or len(txt) < 1000:
        return False
    if not title_part:
        return True
    return title_part[:20] in txt


def revoke(news_id, regenerate=True):
    """撤销挂网：后台删除该条信息，再重新生成列表页，公开页即消失。"""
    with _lock:
        steps = []
        a, cfg = _session_for("auditor")
        r = a.get(cfg["base"] + "/managernjyy-News-del-id-%d.html" % int(news_id), timeout=60)
        _check(r.text, "删除信息")
        steps.append("已删除 id=%s" % news_id)
        if regenerate:
            ok, total = gen_lists(a, cfg)
            steps.append("已重建列表页 %d/%d" % (ok, total))
        gone = not verify("%s/News/info/id/%d.html" % (cfg["base"], int(news_id)))
        return {"news_id": int(news_id), "steps": steps, "gone": gone}


def status(news_id):
    """查一条记录在后台是否还在、是否已审核。"""
    with _lock:
        a, cfg = _session_for("auditor")
        html = a.get(cfg["base"] + "/managernjyy-News-lists-sort-%d.html" % SORT_ID,
                     timeout=30).text
        for tr in re.findall(r"<tr.*?</tr>", html, re.S):
            if 'value="%d"' % int(news_id) in tr:
                marks = re.findall(r">【([^】]+)】<", tr)
                return {"exists": True, "audited": "已审核" in marks, "marks": marks}
        return {"exists": False, "audited": False, "marks": []}


def docx_to_html(blob):
    """把 PMS 生成的公告 Word 转成正文 HTML。

    人工做法是「用 Word 原格式粘过去」，mammoth 转出来的结构化 HTML
    比 Word 粘贴的那堆 mso 样式干净，段落层次一样在。
    """
    import mammoth
    res = mammoth.convert_to_html(io.BytesIO(blob))
    html = res.value or ""
    # 老 CMS 的正文区按 16px 宋体渲染，补一层容器免得字号忽大忽小
    return ('<div style="font-family:宋体,SimSun;font-size:16px;line-height:1.8">%s</div>'
            % html)
