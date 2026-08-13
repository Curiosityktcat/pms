"""rd-web 常驻登录会话池。

要解决的问题：每提交一次就重新登录一次，账号很快被站点判定「登录太频繁」而限流，
一限流所有自动化就全停。

为什么不用 storage_state（这是本项目踩过的坑，别再踩回去）：
    人员选择组件 choosePerson_new 的 user_id/token **只在真实登录过程中注入内存**，
    不落 cookies / localStorage / sessionStorage。带着序列化的旧会话进来会跳过登录，
    结果就是经办人弹框「我的」部门树永远为空 →「未找到经办人」。
    实测同一会话文件 30 分钟后即坏。

所以这里的做法是：**保持浏览器活着，而不是把会话存下来**。
每个账号常驻一个 Playwright browser + context + page，登录一次之后就一直留着；
后续任务复用同一个 page，靠 SPA 内部点击导航（不做整页 goto，否则内存态会丢）。
两个账号 = 两个互不相干的上下文，可以同时在线。

生命周期：
    · 首次使用 → 真实登录，记下时间
    · 再次使用 → 先探活（页面还在、还认得出登录态），活着就直接复用，一次登录都不用
    · 超过 MAX_AGE_SEC 或探活失败 → 关掉重开重新登录
    · 长时间没人用（IDLE_CLOSE_SEC）→ 主动关掉，不白占内存

线程安全：每个账号一把锁，同一账号的任务排队执行（rd-web 本来也不能并发操作同一登录态），
不同账号之间互不阻塞。
"""
import threading
import time

# 与改造前一致的 UA（rd-web 对 UA 不敏感，但没理由改动能跑通的东西）
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# 会话最长存活时间：超过就重新登录一次，避免站点侧 session 悄悄失效
MAX_AGE_SEC = 6 * 60 * 60          # 6 小时
# 空闲多久就主动关掉浏览器释放内存
IDLE_CLOSE_SEC = 2 * 60 * 60       # 2 小时
# 探活超时
PING_TIMEOUT_MS = 8000

_pool: dict = {}                    # {loginuser: _Session}
_pool_lock = threading.Lock()


class _Session:
    def __init__(self, loginuser):
        self.loginuser = loginuser
        self.lock = threading.RLock()   # 同账号任务串行
        self.pw = None
        self.browser = None
        self.ctx = None
        self.page = None
        self.logged_at = 0.0
        self.last_used = 0.0
        self.login_count = 0

    # ── 内部：真正开一个浏览器并登录 ──────────────────────────
    def _open(self, password, login_fn):
        """浏览器参数必须与改造前逐项一致，一个都不能少。

        踩过的坑：图省事用了 chromium 默认参数（默认视口 1280x720），
        结果人员选择框「部门树为空」——因为 _fill_officer 是靠**写死的像素坐标窗口**
        （r.y<140 / r.x>850 / 550<x<900）在页面上找节点的，那套阈值是按
        1920x1080 量出来的。视口一小，节点全落在窗口外，看起来就像树是空的。
        """
        self._close_quiet()
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            channel="chrome",          # 真 Chrome，与改造前一致
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        self.ctx = self.browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},   # 人员选择框的坐标阈值依赖它
            accept_downloads=True,
        )
        self.page = self.ctx.new_page()
        login_fn(self.page, self.ctx, self.loginuser, password, None)
        self.logged_at = time.time()
        self.last_used = time.time()
        self.login_count += 1

    def _close_quiet(self):
        for obj, meth in ((self.ctx, "close"), (self.browser, "close"), (self.pw, "stop")):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:
                pass
        self.pw = self.browser = self.ctx = self.page = None

    # ── 探活：页面还在、还是登录态吗 ───────────────────────────
    def _alive(self):
        if self.page is None:
            return False
        if time.time() - self.logged_at > MAX_AGE_SEC:
            return False
        try:
            if self.page.is_closed():
                return False
            body = self.page.inner_text("body", timeout=PING_TIMEOUT_MS) or ""
        except Exception:
            return False
        # 掉登录态时页面会回到登录页（出现账号/密码框），或菜单整体消失
        if "登录" in body and ("密码" in body or "验证码" in body):
            return False
        return "内江市第一人民医院" in body or "首页" in body

    def acquire(self, password, login_fn, home_url=None):
        """拿到一个已登录的 page。已有活会话就直接复用，否则重新登录。

        返回 (page, reused: bool)
        """
        with self.lock:
            if self._alive():
                self.last_used = time.time()
                # 回到首页（SPA 内部导航，不整页 reload，保住内存里的 token）
                if home_url:
                    try:
                        self.page.evaluate(
                            """() => {
                                const el = [...document.querySelectorAll('*')].find(e =>
                                    e.children.length <= 3 && e.innerText.trim() === '首页'
                                    && e.getBoundingClientRect().width > 0);
                                if (el) el.click();
                            }"""
                        )
                        self.page.wait_for_timeout(800)
                    except Exception:
                        pass
                return self.page, True
            self._open(password, login_fn)
            return self.page, False

    def invalidate(self):
        with self.lock:
            self._close_quiet()
            self.logged_at = 0

    def info(self):
        return {
            "loginuser": self.loginuser,
            "alive": self.page is not None and not (self.page.is_closed() if self.page else True),
            "logged_at": self.logged_at,
            "age_sec": int(time.time() - self.logged_at) if self.logged_at else None,
            "idle_sec": int(time.time() - self.last_used) if self.last_used else None,
            "login_count": self.login_count,
        }


def _get(loginuser) -> _Session:
    with _pool_lock:
        s = _pool.get(loginuser)
        if s is None:
            s = _Session(loginuser)
            _pool[loginuser] = s
        return s


def session_for(loginuser):
    """取（或创建）某账号的会话对象。调用方拿它的 lock + acquire。"""
    return _get(loginuser)


def status():
    """给运维/前端看的会话状态。不含任何凭据。"""
    with _pool_lock:
        out = []
        for u, s in _pool.items():
            d = s.info()
            d["loginuser_masked"] = (u[:3] + "****" + u[-4:]) if len(u) >= 7 else u
            d.pop("loginuser", None)
            out.append(d)
        return out


def close_idle():
    """回收空闲会话。由后台线程定期调用。"""
    now = time.time()
    with _pool_lock:
        items = list(_pool.items())
    for u, s in items:
        if s.last_used and now - s.last_used > IDLE_CLOSE_SEC:
            s.invalidate()


def start_reaper():
    """起一个守护线程定期回收空闲会话，避免浏览器长期空占内存。"""
    def _loop():
        while True:
            time.sleep(600)
            try:
                close_idle()
            except Exception:
                pass
    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    return t
