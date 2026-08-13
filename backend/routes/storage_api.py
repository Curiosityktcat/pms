# -*- coding: utf-8 -*-
"""对象存储直传/签名接口。

**存在的意义**：公网走 cloudflared，免费版请求体 100MB 硬限，大附件传不上去（413）。
让浏览器**直接 PUT 到 OSS**、字节不经过 PMS，这个限制就消失了，也不占服务器带宽。

安全口径：
  · 必须登录；对象键由**服务端**按模块+项目拼好，前端只能用、改不了（策略里 eq $key 钉死）；
  · bucket 私有读，下载一律走**限时签名 URL**，不发长期凭据到浏览器；
  · 本地模式下这些接口原样返回「未启用」，前端据此回落到老的直传 PMS 流程。
"""
import datetime
import os
import re
import uuid

from flask import Blueprint, jsonify, request, session, redirect

from routes.utils import login_required
from services import upload_relay
from services import storage

bp = Blueprint("storage_api", __name__)

# 允许直传的模块 → 相对 PMS 根的目录。**白名单，前端传别的一律拒**，
# 免得有人把对象键指到 uploads/project_distribution 之外去覆盖别人的文件。
MODULE_DIRS = {
    "project_review": "uploads/project_review",       # 8.5 评审资料，文件最大
    "bid_review": "uploads/bid_review",               # 投标文件审核
    "procurement_doc": "uploads/procurement_doc",
    "procurement_result": "uploads/procurement_result",
    "contracts": "uploads/contracts",
    "inquiry": "询价附件/上传",
    # 中转暂存区：不是最终落点，业务接口取走后即删（见 services/upload_relay.py）
    "staging": upload_relay.STAGING_PREFIX,
}
ALLOWED_EXT = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
               ".jpg", ".jpeg", ".png", ".zip", ".rar", ".7z", ".wps", ".et"}
MAX_MB = int(os.environ.get("UPLOAD_MAX_MB") or "500")
# 局域网客户端是否强制走本地磁盘（默认开）。内网到 .12 只有 2ms、千兆、零流量费，
# 绕去成都的 OSS 纯属倒退；OSS 是给公网用户解决跨境慢和隧道 100MB 限制的。
LAN_USE_LOCAL = (os.environ.get("LAN_USE_LOCAL") or "1") == "1"


def client_ip() -> str:
    """真实客户端 IP。经 cloudflared 进来时 remote_addr 是 127.0.0.1，
    真身在 CF-Connecting-IP / X-Forwarded-For 里。"""
    for h in ("CF-Connecting-IP", "X-Forwarded-For", "X-Real-IP"):
        v = request.headers.get(h)
        if v:
            return v.split(",")[0].strip()
    return request.remote_addr or ""


# **医院内网用的 172.1.0.0/16 并不是 RFC1918 私有段**（私有段是 10/8、172.16-31/12、
# 192.168/16），所以不能只靠 ipaddress.is_private 判断——实测 172.1.14.88 会被判成公网。
# 这里显式列出本单位网段，可用 env LAN_CIDRS 覆盖（逗号分隔）。
LAN_CIDRS = [c.strip() for c in (os.environ.get("LAN_CIDRS") or
             "127.0.0.0/8,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,172.1.0.0/16").split(",") if c.strip()]


def is_lan(ip: str) -> bool:
    try:
        import ipaddress
        a = ipaddress.ip_address(ip)
        for c in LAN_CIDRS:
            try:
                if a in ipaddress.ip_network(c, strict=False):
                    return True
            except ValueError:
                continue
        return a.is_loopback
    except ValueError:
        return False


def _safe_name(name: str) -> str:
    name = os.path.basename(name or "").strip()
    name = re.sub(r"[\\/:*?\"<>|\r\n\t]", "_", name)
    return name[:120] or "file"


# 暂存区兜底清理：正常流程「取走即删」，这里收拾「传了但没点保存」的漏网对象。
# 挂在签名接口上顺带跑，最多一小时一次，不额外起定时任务（单 worker，进程内计时够用）。
_last_sweep = [0.0]


def _sweep_staging_occasionally(min_interval: int = 3600):
    import time as _t
    now = _t.time()
    if now - _last_sweep[0] < min_interval:
        return
    _last_sweep[0] = now
    try:
        n = upload_relay.sweep()
        if n:
            print(f"[storage] 清理过期暂存对象 {n} 个", flush=True)
    except Exception as e:
        print(f"[storage] 暂存区清理失败（不影响上传）：{e}", flush=True)


@bp.route("/api/storage/status", methods=["GET"])
@login_required
def storage_status():
    """前端据此决定走直传还是老流程。"""
    st = storage.stat()
    ip = client_ip()
    lan = LAN_USE_LOCAL and is_lan(ip)
    return jsonify({"ok": True, "direct_upload": st["oss_enabled"] and not lan,
                    "max_mb": MAX_MB, "backend": st["backend"],
                    "client_ip": ip, "lan": lan})


@bp.route("/api/storage/sign-upload", methods=["POST"])
@login_required
def sign_upload():
    """签直传策略。body: {module, filename, project_id?}
    返回 {ok, direct:true, form:{...}, rel_path} —— 前端拿 form 直接 POST 到 OSS，
    成功后把 rel_path 回填给业务接口入库（业务表存的还是 rel_path，语义不变）。"""
    d = request.get_json(force=True, silent=True) or {}
    module = str(d.get("module") or "").strip()
    if module not in MODULE_DIRS:
        return jsonify({"ok": False, "error": f"不支持的模块 {module}"}), 400
    filename = _safe_name(d.get("filename"))
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({"ok": False, "error": f"不支持的文件格式 {ext}"}), 400

    if not storage.oss_enabled():
        # 本地模式：告诉前端走老流程（POST 到 PMS 自己的上传接口）
        return jsonify({"ok": True, "direct": False,
                        "reason": "对象存储未启用，走服务器中转上传"})

    ip = client_ip()
    if LAN_USE_LOCAL and is_lan(ip):
        # 内网用户：直连 .12 只有 2ms、千兆、不产生流量费，比绕成都快得多
        return jsonify({"ok": True, "direct": False,
                        "reason": f"局域网访问（{ip}），走本地更快且不计流量费"})

    stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
    _sweep_staging_occasionally()
    if module == "staging":
        # 中转直传：先落到本人专属暂存区，业务接口再把它拉回本地原路径。
        # 给那些「文件必须在本地磁盘」的模块（合同/采购结果等）用，见 services/upload_relay.py
        rel = upload_relay.staging_rel(filename, stamp, uuid.uuid4().hex[:8])
    else:
        pid = re.sub(r"\D", "", str(d.get("project_id") or "")) or "misc"
        rel = f"{MODULE_DIRS[module]}/{pid}/{stamp}_{uuid.uuid4().hex[:8]}_{filename}"
    form = storage.post_policy(rel, max_mb=MAX_MB)
    return jsonify({"ok": True, "direct": True, "rel_path": rel, "form": form,
                    "filename": filename})


@bp.route("/api/storage/file", methods=["GET"])
@login_required
def get_file():
    """按 rel_path 取文件：在 OSS 上就 302 到限时签名 URL，在本地就走原有预览逻辑。
    ?inline=1 内联预览，否则下载。**只认已入库的 rel_path 由业务接口转调**，
    这里额外做一次目录白名单校验，避免被拿来读任意路径。"""
    rel = (request.args.get("path") or "").replace("\\", "/").lstrip("/")
    if not rel or ".." in rel:
        return jsonify({"ok": False, "error": "路径不合法"}), 400
    if not any(rel.startswith(d + "/") for d in MODULE_DIRS.values()):
        return jsonify({"ok": False, "error": "路径不在允许范围内"}), 403
    where, val = storage.resolve(rel)
    if not where:
        return jsonify({"ok": False, "error": "文件不存在"}), 404
    inline = request.args.get("inline") in ("1", "true")
    name = os.path.basename(rel)
    if where == "oss":
        return redirect(storage.signed_url(rel, filename=name, inline=inline), code=302)
    from services.office_convert import send_preview
    from flask import send_file
    return send_preview(val, name) if inline else send_file(
        val, as_attachment=True, download_name=name)
