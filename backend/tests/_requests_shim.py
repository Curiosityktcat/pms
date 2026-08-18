"""让老验收脚本不再走 HTTP、改成进程内 test_client 的垫片。

为什么要这个：老脚本用 requests 打 http://127.0.0.1:1574，而 1574 挂着公网、
登录有滑块，脚本一律登不进去。以前是临时把 1574 的滑块关掉跑——那等于让公网
裸奔一段时间，不能再这么干（见 memory: pms-test-instance-1574）。

用法：脚本里把 `import requests` 换成
    import _requests_shim as requests
    requests.bind(app)          # app = create_app() 之后
并把 BASE 设成 ""。其余代码一个字不用改。
"""
_APP = None


def bind(app):
    global _APP
    _APP = app


class _Resp:
    """把 Flask 的响应装成 requests.Response 的样子。"""

    def __init__(self, r):
        self._r = r

    @property
    def status_code(self):
        return self._r.status_code

    @property
    def content(self):
        return self._r.data

    @property
    def text(self):
        return self._r.get_data(as_text=True)

    def json(self):
        v = self._r.get_json(silent=True)
        if v is None:
            raise ValueError("响应不是 JSON：" + self.text[:120])
        return v


def _to_werkzeug_file(spec):
    """requests 的 files 是 (文件名, 内容, 类型)，Werkzeug 要的是 (内容流, 文件名, 类型)
    —— 前两个是反的。照搬过去会把文件名当成路径去开，报 FileNotFoundError。"""
    import io as _io
    if isinstance(spec, (tuple, list)):
        parts = list(spec) + [None] * (3 - len(spec))
        filename, content, ctype = parts[0], parts[1], parts[2]
        if isinstance(content, (bytes, bytearray)):
            content = _io.BytesIO(content)
        elif isinstance(content, str):
            content = _io.BytesIO(content.encode("utf-8"))
        return (content, filename, ctype) if ctype else (content, filename)
    return spec


class Session:
    def __init__(self):
        if _APP is None:
            raise RuntimeError("先调用 _requests_shim.bind(app)")
        self._c = _APP.test_client()

    @staticmethod
    def _path(url):
        # 老脚本写的是 f"{BASE}{path}"，BASE 置空后就是纯 path；
        # 万一还带着 http://host:port 前缀也剥掉，省得改不干净。
        if "://" in url:
            url = "/" + url.split("://", 1)[1].split("/", 1)[1]
        return url or "/"

    def _call(self, method, url, **kw):
        kw.pop("timeout", None)
        kw.pop("allow_redirects", None)
        if "params" in kw:
            kw["query_string"] = kw.pop("params")
        if "files" in kw:
            payload = dict(kw.pop("data", None) or {})
            for field, spec in (kw.pop("files") or {}).items():
                payload[field] = _to_werkzeug_file(spec)
            kw["data"] = payload
            kw["content_type"] = "multipart/form-data"
        return _Resp(getattr(self._c, method)(self._path(url), **kw))

    def get(self, url, **kw):
        return self._call("get", url, **kw)

    def post(self, url, **kw):
        return self._call("post", url, **kw)

    def put(self, url, **kw):
        return self._call("put", url, **kw)

    def patch(self, url, **kw):
        return self._call("patch", url, **kw)

    def delete(self, url, **kw):
        return self._call("delete", url, **kw)


def get(url, **kw):
    return Session().get(url, **kw)


def post(url, **kw):
    return Session().post(url, **kw)
