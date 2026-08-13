"""系统说明书 API：把 ~/pms/docs/*.md 渲染成 HTML 给前端看。

设计意图：文档以 markdown 文件存放，**改文件即生效**——不用重新构建前端、不用重启服务，
后续维护只要往 docs/ 里加一个 .md 或改一改内容就行。

文件头部可写 YAML front matter（可选）：
    ---
    title: 显示标题
    order: 20        # 排序，小的在前
    summary: 一句话摘要
    ---
"""
import os
import re
import subprocess

from flask import Blueprint, jsonify, session

from routes.utils import login_required

bp = Blueprint("sysdocs", __name__, url_prefix="/api/sysdocs")

# 说明书含系统内部实现、端口、部署方式等信息，仅限白名单用户查看（默认只有「黄新博」）。
# 需要放给别人时改 env SYS_DOCS_USERS（逗号分隔），不要改代码硬编码。
SYS_DOCS_USERS = [u.strip() for u in os.environ.get(
    "SYS_DOCS_USERS", "黄新博").split(",") if u.strip()]


@bp.before_request
def _guard():
    """登录之外再加一道人名白名单。"""
    if session.get("user") and session.get("user") not in SYS_DOCS_USERS:
        return jsonify(ok=False, error="系统说明书未对当前账号开放"), 403

DOCS_DIR = os.environ.get(
    "PMS_DOCS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "docs"),
)
DOCS_DIR = os.path.abspath(DOCS_DIR)

_cache = {}          # slug -> (mtime, html)
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)


def _parse(path):
    """读一篇 md，拆出 front matter 与正文。"""
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    meta, body = {}, raw
    m = _FM_RE.match(raw)
    if m:
        body = raw[m.end():]
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
    return meta, body


def _slug(fn):
    return os.path.splitext(fn)[0]


def _list_files():
    if not os.path.isdir(DOCS_DIR):
        return []
    return sorted(f for f in os.listdir(DOCS_DIR) if f.endswith(".md"))


@bp.get("")
@login_required
def list_docs():
    """目录：给左侧导航用。"""
    items = []
    for fn in _list_files():
        path = os.path.join(DOCS_DIR, fn)
        meta, _ = _parse(path)
        items.append({
            "slug": _slug(fn),
            "title": meta.get("title") or _slug(fn),
            "summary": meta.get("summary", ""),
            "order": int(meta.get("order") or 999),
            "updated_at": int(os.path.getmtime(path)),
        })
    items.sort(key=lambda x: (x["order"], x["slug"]))
    return jsonify(ok=True, docs=items)


@bp.get("/<slug>")
@login_required
def get_doc(slug):
    """单篇：pandoc 渲染成 HTML（按 mtime 缓存，改文件即刷新）。"""
    if not re.fullmatch(r"[\w一-鿿.-]{1,80}", slug or ""):
        return jsonify(ok=False, error="非法文档名"), 400
    path = os.path.join(DOCS_DIR, slug + ".md")
    if not os.path.isfile(path):
        return jsonify(ok=False, error="文档不存在"), 404

    mtime = os.path.getmtime(path)
    hit = _cache.get(slug)
    if hit and hit[0] == mtime:
        html = hit[1]
    else:
        meta, body = _parse(path)
        try:
            html = subprocess.check_output(
                ["pandoc", "-f", "markdown+pipe_tables+task_lists", "-t", "html",
                 "--highlight-style", "tango"],
                input=body.encode("utf-8"), timeout=30,
            ).decode("utf-8")
        except Exception as e:
            return jsonify(ok=False, error=f"渲染失败：{e}"), 500
        _cache[slug] = (mtime, html)

    meta, _ = _parse(path)
    return jsonify(ok=True, slug=slug, title=meta.get("title") or slug,
                   summary=meta.get("summary", ""),
                   updated_at=int(mtime), html=html)
