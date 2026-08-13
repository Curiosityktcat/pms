"""Office 文档服务端转 PDF（预览用）。

场景：`.doc` / `.xls` / `.ppt` 等旧二进制格式前端无法渲染（docx-preview / SheetJS
只吃新版 OOXML），统一用本机 LibreOffice(soffice) 转成 PDF 内联预览。
转换结果按「源文件绝对路径 + mtime + size」缓存到磁盘，重复预览不重复转换。

对外主入口：
    to_pdf(src_path) -> pdf_path            # 转换（带缓存），失败抛异常
    send_preview(path, download_name)       # Flask 端点统一预览响应（自动/按需转 PDF）
"""
import hashlib
import mimetypes
import os
import subprocess
import threading

_PMS_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_CACHE_DIR = os.path.join(_PMS_ROOT, "uploads", "_preview_pdf_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

# 前端无渲染器的格式：默认自动转 PDF 预览
# 注意 .xls 不在此列——前端用 SheetJS 渲染成可交互表格（渲染失败再走 ?pdf=1 兜底），
# 若放这里会让每个 .xls 都被转成 PDF、前端 SheetJS 拿到 PDF 反而失败。
LEGACY_OFFICE = {".doc", ".ppt", ".wps", ".et", ".dps", ".rtf"}
# 前端能渲染，仅在 ?pdf=1 兜底时才转：.docx/.xlsx/.xls 前端渲染，.pptx 无渲染器但也走 pdf=1
MODERN_OFFICE = {".docx", ".xlsx", ".xls", ".pptx"}
CONVERTIBLE = LEGACY_OFFICE | MODERN_OFFICE

_soffice_lock = threading.Lock()   # soffice 同一 profile 不能并发，串行化


def _cache_key(src_path: str) -> str:
    st = os.stat(src_path)
    raw = f"{os.path.abspath(src_path)}|{st.st_mtime_ns}|{st.st_size}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def to_pdf(src_path: str) -> str:
    """把 src_path 转成 PDF，返回 PDF 路径（带磁盘缓存）。失败抛 RuntimeError。"""
    if not os.path.exists(src_path):
        raise RuntimeError(f"源文件不存在: {src_path}")
    out_pdf = os.path.join(_CACHE_DIR, _cache_key(src_path) + ".pdf")
    if os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0:
        return out_pdf

    with _soffice_lock:
        # 二次检查（可能已被并发请求转好）
        if os.path.exists(out_pdf) and os.path.getsize(out_pdf) > 0:
            return out_pdf
        # 每次用独立 user profile，避免与桌面/其他任务的 soffice 抢锁
        profile = os.path.join(_CACHE_DIR, ".lo_profile")
        cmd = [
            "soffice", "--headless", "--norestore",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to", "pdf", "--outdir", _CACHE_DIR, src_path,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=120)
        except subprocess.TimeoutExpired:
            raise RuntimeError("文档转换超时（LibreOffice）")
        # soffice 用源文件名命名输出，需重命名到缓存 key
        base = os.path.splitext(os.path.basename(src_path))[0] + ".pdf"
        produced = os.path.join(_CACHE_DIR, base)
        if os.path.exists(produced) and os.path.getsize(produced) > 0:
            if produced != out_pdf:
                os.replace(produced, out_pdf)
            return out_pdf
        err = (proc.stderr or b"").decode("utf-8", "ignore")[:200]
        raise RuntimeError(f"文档转换失败：{err or 'LibreOffice 未产出 PDF'}")


def send_preview(path: str, download_name: str, mimetype: str = None):
    """Flask 预览端点统一响应：

    - 旧二进制 Office（.doc/.xls/.ppt…）→ 自动转 PDF 内联预览
    - 新版 Office（.docx/.xlsx/.pptx）默认原样发送（前端渲染），带 ?pdf=1 时转 PDF 兜底
    - 其它类型原样发送
    转换失败自动回退为发送原文件，绝不因转换报错而让预览白屏。
    """
    from flask import request, send_file
    ext = os.path.splitext(download_name or path)[1].lower()
    force_pdf = request.args.get("pdf") in ("1", "true", "yes")
    want_pdf = ext in LEGACY_OFFICE or (force_pdf and ext in MODERN_OFFICE)
    if want_pdf:
        try:
            pdf = to_pdf(path)
            pdf_name = os.path.splitext(os.path.basename(download_name or path))[0] + ".pdf"
            return send_file(pdf, mimetype="application/pdf",
                             as_attachment=False, download_name=pdf_name)
        except Exception:
            pass  # 回退发送原文件
    if mimetype is None:
        mimetype = mimetypes.guess_type(download_name or path)[0]
    return send_file(path, mimetype=mimetype, as_attachment=False,
                     download_name=download_name)
