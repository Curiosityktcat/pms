# -*- coding: utf-8 -*-
"""统一存储层：本地磁盘 ←→ 阿里云 OSS 的切换点。

**为什么要有这层**（2026-08-04）：
  · 公网走 cloudflared 隧道，免费版有 **100MB 请求体硬限**，大附件传不上去（413）；
    跨境回源 242ms，下载也慢。前端直传对象存储可以把这两件事一起解决。
  · 但 PMS 库里存的是 `saved_name` / `file_path`，**文件名改一个字就断链**（血泪铁律）。
    所以这层的契约是：**以 rel_path 为唯一键，库里存什么不变**，只改"字节实际落在哪"。

**迁移策略是渐进的，不做一次性搬迁**：
  读取时 `resolve()` 先看首选后端，没有就回落另一个 → 历史文件留在本地照常能读，
  新文件写 OSS；哪天想搬历史文件，后台慢慢 `migrate()` 即可，期间业务不中断。

配置（全部走环境变量，未配则自动是纯本地模式，行为与改造前完全一致）：
  STORAGE_BACKEND = local | oss     默认 local
  OSS_ENDPOINT    = oss-cn-chengdu.aliyuncs.com
  OSS_BUCKET      = pms-files
  OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET
  OSS_PREFIX      = pms/            对象键前缀，便于同 bucket 多用途隔离
  OSS_URL_EXPIRES = 600             签名 URL 有效期（秒）
"""
import os
import shutil
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PMS_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
# **锚点是 PMS 根目录**，不是某个 uploads 目录：PMS 实际有两个附件根
# （`~/pms/uploads/...` 和 `~/pms/backend/uploads/...`，不同模块各用各的），
# 还有 `询价附件/上传/...` 这种平级目录。统一用"相对 PMS 根"的 rel_path 才都能表达，
# 而且 inquiry 模块库里存的 filepath 本来就是这个口径，零转换。
UPLOAD_ROOT = PMS_ROOT

BACKEND = (os.environ.get("STORAGE_BACKEND") or "local").strip().lower()
OSS_ENDPOINT = (os.environ.get("OSS_ENDPOINT") or "").strip()
OSS_BUCKET = (os.environ.get("OSS_BUCKET") or "").strip()
OSS_AK = (os.environ.get("OSS_ACCESS_KEY_ID") or "").strip()
OSS_SK = (os.environ.get("OSS_ACCESS_KEY_SECRET") or "").strip()
OSS_PREFIX = (os.environ.get("OSS_PREFIX") or "pms/").strip().lstrip("/")
URL_EXPIRES = int(os.environ.get("OSS_URL_EXPIRES") or "600")

_bucket = None
_lock = threading.Lock()


def oss_enabled() -> bool:
    return BACKEND == "oss" and all([OSS_ENDPOINT, OSS_BUCKET, OSS_AK, OSS_SK])


def _b():
    """惰性建 bucket 客户端（没配 OSS 时整个模块零依赖，本地模式不受影响）。"""
    global _bucket
    if _bucket is None:
        with _lock:
            if _bucket is None:
                import oss2
                auth = oss2.Auth(OSS_AK, OSS_SK)
                # **endpoint 必须带 https://**：不带协议时 oss2 默认走 http，
                # 签出来的 URL 就是 http://，而 PMS 页面是 https，
                # 浏览器会以「混合内容」为由直接拦掉这个 302 跳转（实测踩到）。
                ep = OSS_ENDPOINT if "://" in OSS_ENDPOINT else "https://" + OSS_ENDPOINT
                _bucket = oss2.Bucket(auth, ep, OSS_BUCKET)
    return _bucket


def _key(rel_path: str) -> str:
    return OSS_PREFIX + rel_path.replace("\\", "/").lstrip("/")


def local_path(rel_path: str) -> str:
    return os.path.join(UPLOAD_ROOT, rel_path.replace("\\", "/").lstrip("/"))


# ── 写 ──────────────────────────────────────────────────────────
def save(fileobj, rel_path: str) -> str:
    """把上传的文件存进当前后端。返回 rel_path（库里存的还是它，语义不变）。"""
    if oss_enabled():
        _b().put_object(_key(rel_path), fileobj)
        return rel_path
    p = local_path(rel_path)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if hasattr(fileobj, "save"):          # werkzeug FileStorage
        fileobj.save(p)
    else:
        with open(p, "wb") as f:
            shutil.copyfileobj(fileobj, f)
    return rel_path


def delete(rel_path: str) -> None:
    """两个后端都删——迁移期同一份文件可能两边都有，只删一边会留幽灵。"""
    if oss_enabled():
        try:
            _b().delete_object(_key(rel_path))
        except Exception:
            pass
    p = local_path(rel_path)
    if os.path.exists(p):
        try:
            os.remove(p)
        except OSError:
            pass


# ── 读 ──────────────────────────────────────────────────────────
def exists(rel_path: str) -> bool:
    if oss_enabled():
        try:
            if _b().object_exists(_key(rel_path)):
                return True
        except Exception:
            pass
    return os.path.exists(local_path(rel_path))


def resolve(rel_path: str) -> tuple:
    """返回 (位置, 值)：('oss', 对象键) 或 ('local', 绝对路径) 或 (None, None)。
    迁移期先问首选后端，没有就回落 —— 历史文件不用搬也能读。"""
    if oss_enabled():
        try:
            if _b().object_exists(_key(rel_path)):
                return "oss", _key(rel_path)
        except Exception:
            pass
    p = local_path(rel_path)
    if os.path.exists(p):
        return "local", p
    return None, None


def signed_url(rel_path: str, filename: str = "", inline: bool = False,
               expires: int = None) -> str:
    """给 OSS 上的对象签一个限时 URL。**bucket 必须私有读**，
    这些是医院采购文件（历史上还夹带过身份证照片），绝不能设公共读。"""
    if not oss_enabled():
        return ""
    import urllib.parse
    params = {}
    if filename:
        disp = "inline" if inline else "attachment"
        quoted = urllib.parse.quote(filename)
        params["response-content-disposition"] = f"{disp}; filename*=UTF-8''{quoted}"
    return _b().sign_url("GET", _key(rel_path), expires or URL_EXPIRES,
                         params=params, slash_safe=True)


# ── 前端直传（绕开 cloudflared 的 100MB 限制，这是本次改造的核心目的）──
def post_policy(rel_path: str, max_mb: int = 500, expires: int = 900) -> dict:
    """签一份 PostObject 表单策略：浏览器拿着它**直接 PUT 到 OSS**，字节不经过 PMS，
    因此不受隧道请求体限制、也不占用服务器带宽。
    策略把 key 钉死成指定 rel_path（不是前缀），前端改不了落点。"""
    if not oss_enabled():
        return {}
    import base64
    import datetime
    import hmac
    import hashlib
    import json
    expire_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=expires)
    policy = {
        "expiration": expire_at.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "conditions": [
            {"bucket": OSS_BUCKET},
            ["eq", "$key", _key(rel_path)],
            ["content-length-range", 0, max_mb * 1024 * 1024],
        ],
    }
    doc = base64.b64encode(json.dumps(policy).encode()).decode()
    sig = base64.b64encode(
        hmac.new(OSS_SK.encode(), doc.encode(), hashlib.sha1).digest()).decode()
    host_ep = OSS_ENDPOINT.split("://")[-1]
    return {
        "host": f"https://{OSS_BUCKET}.{host_ep}",
        "key": _key(rel_path),
        "policy": doc,
        "OSSAccessKeyId": OSS_AK,
        "signature": sig,
        "expires_in": expires,
        "max_mb": max_mb,
    }


# ── 迁移工具（后台慢慢搬，不影响业务）────────────────────────────
def migrate_up(rel_path: str) -> bool:
    """把一个本地文件搬到 OSS（搬完不删本地，确认无误后再清）。"""
    if not oss_enabled():
        return False
    p = local_path(rel_path)
    if not os.path.exists(p):
        return False
    with open(p, "rb") as f:
        _b().put_object(_key(rel_path), f)
    return True


def stat() -> dict:
    return {"backend": BACKEND, "oss_enabled": oss_enabled(),
            "bucket": OSS_BUCKET, "endpoint": OSS_ENDPOINT, "prefix": OSS_PREFIX,
            "upload_root": UPLOAD_ROOT}
