"""文件识别（OCR）：把上传的 PDF/图片转发给局域网 PaddleOCR-VL 服务，返回 Markdown 文本。

识别服务部署在另一台带 GPU 的机器上（默认 http://192.168.1.12:8118），
可用环境变量 PMS_OCR_URL 覆盖。本路由仅做鉴权 + 转发 + 友好错误包装，
不在本机做任何模型推理。
"""
import os
import requests
from flask import Blueprint, request, jsonify
from routes.utils import login_required

bp = Blueprint("ocr", __name__, url_prefix="/api/ocr")

# OCR 服务地址（PaddleOCR-VL，见 ~/cgb/ocr_server.py）。可用环境变量覆盖。
OCR_BASE = os.environ.get("PMS_OCR_URL", "http://192.168.1.12:8118").rstrip("/")

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
# 识别耗时随页数增长，给足超时（秒）
RECOGNIZE_TIMEOUT = 300


@bp.route("/health", methods=["GET"])
@login_required
def health():
    """探测 OCR 服务是否在线、模型是否已加载。"""
    try:
        resp = requests.get(f"{OCR_BASE}/health", timeout=5)
        j = resp.json()
        return jsonify({"ok": True, "data": {
            "online": bool(j.get("model_loaded")),
            "server": OCR_BASE,
        }})
    except Exception:
        return jsonify({"ok": True, "data": {"online": False, "server": OCR_BASE}})


@bp.route("/recognize", methods=["POST"])
@login_required
def recognize():
    """接收单个 PDF/图片，转发给 OCR 服务，返回识别出的 Markdown。"""
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({
            "ok": False,
            "error": f"不支持的文件格式：{ext or '未知'}（仅支持 PDF / 图片）",
        }), 400

    try:
        resp = requests.post(
            f"{OCR_BASE}/ocr",
            files={"file": (
                f.filename,
                f.stream,
                f.mimetype or "application/octet-stream",
            )},
            timeout=RECOGNIZE_TIMEOUT,
        )
    except requests.exceptions.ConnectionError:
        return jsonify({
            "ok": False,
            "error": f"识别服务连接失败，请确认 OCR 服务（{OCR_BASE}）已启动",
        }), 502
    except requests.exceptions.Timeout:
        return jsonify({
            "ok": False,
            "error": "识别超时，文件可能过大或页数过多，请稍后重试",
        }), 504
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"调用识别服务失败：{e}"}), 502

    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001
            detail = (resp.text or "")[:300]
        return jsonify({"ok": False, "error": f"识别失败：{detail}"}), 502

    try:
        data = resp.json()
    except Exception:  # noqa: BLE001
        return jsonify({"ok": False, "error": "识别服务返回了非预期的内容"}), 502

    return jsonify({"ok": True, "data": {
        "filename": data.get("filename") or f.filename,
        "pages": data.get("pages"),
        "markdown": data.get("markdown") or "",
    }})
