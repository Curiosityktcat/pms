# -*- coding: utf-8 -*-
"""OSS 中转直传：绕开 Cloudflare，但业务代码几乎不用改。

**为什么需要**：公网走 cloudflared 上传实测 5MB 要 87 秒、40MB 到 131 秒时被
Cloudflare 免费版的 **100 秒源站超时**掐断（HTTP 524）；同一台机器同一时刻直传
阿里云 OSS（成都）只要 4.3 秒。所以大文件必须绕开这条隧道。

**为什么是中转而不是整体搬到 OSS**：合同、采购结果这些模块的下载、预览、删除、
rd-web 推送等六七处代码都直接按本地路径读文件；把存储整体换掉要连带改动全部读点，
风险大。中转只改「收文件」这一步——浏览器把文件直传到 OSS 暂存区，业务接口从
暂存区把它拉回**原来的本地路径**，落盘之后一切照旧，下载/预览/推送代码一行不动。

**用法**：业务接口把
    f = request.files.get("file")
改成
    f = request.files.get("file") or upload_relay.staged_file()
拿到的对象与 werkzeug 的 FileStorage 同形（有 .filename / .save(路径) / .read()），
后续代码不用动。
"""
import hashlib
import hmac
import os
import shutil

from flask import current_app, request, session

from services import storage

# 暂存区前缀：所有中转对象都落在这下面，用完即删
STAGING_PREFIX = "uploads/_staging"
# 暂存对象兜底清理时限（正常流程用完就删，这是给「传了但没提交」的漏网之鱼准备的）
STAGING_TTL_HOURS = int(os.environ.get("UPLOAD_STAGING_TTL_HOURS") or "24")


def user_slot(user: str = None) -> str:
    """按登录人算一个不可猜的目录名。

    暂存对象的键会回传给服务端，必须防止 A 拿着 B 的键把别人的文件"认领"过来。
    用 SECRET_KEY 派生，猜不出也伪造不了。
    """
    if user is None:
        user = session.get("user") or ""
    secret = (current_app.config.get("SECRET_KEY") or "").encode()
    return hmac.new(secret, f"staging:{user}".encode(), hashlib.sha256).hexdigest()[:16]


def staging_rel(filename: str, stamp: str, rand: str) -> str:
    return f"{STAGING_PREFIX}/{user_slot()}/{stamp}_{rand}_{filename}"


def _key_belongs_to_me(rel: str) -> bool:
    rel = (rel or "").replace("\\", "/").lstrip("/")
    if ".." in rel:
        return False
    return rel.startswith(f"{STAGING_PREFIX}/{user_slot()}/")


class StagedFile:
    """与 werkzeug FileStorage 同形的壳子，字节来自 OSS 暂存区。"""

    def __init__(self, rel: str, filename: str):
        self.rel = rel
        self.filename = filename
        self._stream = None

    # ── FileStorage 兼容面 ────────────────────────────────────
    @property
    def stream(self):
        if self._stream is None:
            self._stream = storage._b().get_object(storage._key(self.rel))
        return self._stream

    def read(self, n=-1):
        return self.stream.read() if n is None or n < 0 else self.stream.read(n)

    def save(self, dst, buffer_size=1024 * 1024):
        """流式拉回本地目标路径，落盘成功后删掉暂存对象。"""
        dst = str(dst)
        d = os.path.dirname(dst)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(dst, "wb") as f:
            shutil.copyfileobj(self.stream, f, buffer_size)
        self.cleanup()

    # ── 收尾 ──────────────────────────────────────────────────
    def cleanup(self):
        try:
            storage._b().delete_object(storage._key(self.rel))
        except Exception:
            pass          # 删不掉不影响业务，兜底清理会收拾


def staged_file(field: str = "oss_key"):
    """如果这次请求是「已直传 OSS」的中转上传，返回 StagedFile，否则 None。

    表单里要带：oss_key=暂存对象 rel_path、original_name=原始文件名。
    """
    rel = (request.form.get(field) or "").replace("\\", "/").lstrip("/")
    if not rel:
        return None
    if not storage.oss_enabled():
        return None
    if not _key_belongs_to_me(rel):
        return None                      # 不是自己的暂存对象，一律不认
    if not storage.exists(rel):
        return None                      # 直传没成功/已过期
    name = (request.form.get("original_name") or os.path.basename(rel)).strip()
    name = os.path.basename(name.replace("\\", "/")) or "file"
    return StagedFile(rel, name)


def sweep(ttl_hours: int = None) -> int:
    """兜底清理：删掉超时仍未被认领的暂存对象。返回删除个数。"""
    if not storage.oss_enabled():
        return 0
    import datetime
    ttl = ttl_hours if ttl_hours is not None else STAGING_TTL_HOURS
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=ttl)
    import oss2
    n = 0
    b = storage._b()
    for obj in oss2.ObjectIterator(b, prefix=storage._key(STAGING_PREFIX + "/")):
        try:
            when = datetime.datetime.fromtimestamp(obj.last_modified, datetime.timezone.utc)
            if when < cutoff:
                b.delete_object(obj.key)
                n += 1
        except Exception:
            continue
    return n
