"""文件识别（OCR）：把上传的 PDF/图片转发给本机 PaddleOCR 服务，返回 Markdown 文本。

识别服务与 PMS 同机部署（paddle-ocr.service，默认 http://127.0.0.1:8118），
可用环境变量 PMS_OCR_URL 覆盖。本路由做鉴权 + 转发 + 计费 + 友好错误包装，
不在本进程做任何模型推理。

双引擎：
- engine=paddle  → PaddleOCR-VL 1.6 大模型（效果好；按 token 计费，价格按 PMS
  系统定价 llm_price_per_million，消耗较大、比较贵；代理机构余额不足会被拦截）
- engine=classic → 传统 PP-OCR（免费，不消耗 token，适合清晰打印件）
"""
import os
import requests
from flask import Blueprint, request, session, jsonify
from routes.utils import login_required

bp = Blueprint("ocr", __name__, url_prefix="/api/ocr")

# OCR 服务地址（见 ~/cgb/ocr_server.py，systemd: paddle-ocr.service）。可用环境变量覆盖。
OCR_BASE = os.environ.get("PMS_OCR_URL", "http://127.0.0.1:8118").rstrip("/")

ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
# 识别耗时随页数增长，给足超时（秒）
RECOGNIZE_TIMEOUT = 300

ENGINE_PATHS = {"paddle": "/ocr", "classic": "/ocr_classic"}
ENGINE_MODEL = {"paddle": "paddleocr-vl-1.6", "classic": "pp-ocr"}


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
            "engines": j.get("engines") or {"paddle": bool(j.get("model_loaded"))},
        }})
    except Exception:
        return jsonify({"ok": True, "data": {"online": False, "server": OCR_BASE}})


@bp.route("/recognize", methods=["POST"])
@login_required
def recognize():
    """接收单个 PDF/图片，转发给 OCR 服务，返回识别出的 Markdown。

    engine=paddle（默认）按 token 计费；engine=classic 免费。
    """
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "未收到文件"}), 400

    engine = (request.form.get("engine") or "paddle").strip()
    if engine not in ENGINE_PATHS:
        return jsonify({"ok": False, "error": f"未知识别引擎：{engine}"}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_EXT:
        return jsonify({
            "ok": False,
            "error": f"不支持的文件格式：{ext or '未知'}（仅支持 PDF / 图片）",
        }), 400

    # 大模型引擎：代理机构余额不足则拦截（内部账号不计费）
    role = session.get("role", "")
    agency_code = session.get("agency_code", "") if role == "agency" else ""
    if engine == "paddle" and agency_code:
        from services.billing import get_balance
        bal = get_balance(agency_code)
        if bal is not None and bal <= 0:
            return jsonify({"ok": False,
                            "error": "AI 余额不足，请联系采购部充值后再使用"
                                     "（或改用免费的传统 OCR）"}), 402

    try:
        resp = requests.post(
            f"{OCR_BASE}{ENGINE_PATHS[engine]}",
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

    out = {
        "filename": data.get("filename") or f.filename,
        "pages": data.get("pages"),
        "markdown": data.get("markdown") or "",
        "engine": engine,
        "result_id": data.get("result_id") or "",   # 导出时嵌回版面图片
    }

    # 大模型引擎：记录用量并按 PMS 定价扣费
    usage = data.get("usage") if engine == "paddle" else None
    if usage:
        from services import llm_usage
        from services.billing import cost_of, get_balance
        llm_usage.record(
            session.get("user", ""),
            session.get("display_name", ""),
            "文件识别(PaddleOCR-VL)",
            ENGINE_MODEL[engine],
            usage,
            agency_code=agency_code,
        )
        out["usage"] = usage
        out["cost"] = round(cost_of(usage.get("total_tokens")), 4)
        if agency_code:
            out["balance"] = round(get_balance(agency_code) or 0, 2)

    return jsonify({"ok": True, "data": out})


@bp.route("/export", methods=["POST"])
@login_required
def export():
    """识别结果导出为 Word / Excel / PDF（转发 OCR 服务，不计费）。"""
    body = request.get_json(silent=True) or {}
    fmt = (body.get("format") or "").lower().strip()
    if fmt not in ("docx", "xlsx", "pdf"):
        return jsonify({"ok": False, "error": f"不支持的导出格式：{fmt}"}), 400
    try:
        resp = requests.post(f"{OCR_BASE}/export", json={
            "markdown": body.get("markdown") or "",
            "format": fmt,
            "filename": body.get("filename") or "ocr",
            "result_id": body.get("result_id") or "",
        }, timeout=180)
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "error": f"导出服务调用失败：{e}"}), 502
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:  # noqa: BLE001
            detail = (resp.text or "")[:300]
        return jsonify({"ok": False, "error": f"导出失败：{detail}"}), 502
    from flask import Response
    return Response(
        resp.content,
        mimetype=resp.headers.get("Content-Type", "application/octet-stream"),
        headers={"Content-Disposition":
                 resp.headers.get("Content-Disposition", "attachment")},
    )
