"""通用大模型客户端（OpenAI 兼容 /v1/chat/completions）。

全系统共用同一套模型配置：与「开标看板」抓取模型相同的 SysConfig 键，
在后台「大模型设置」页配置一次，开标看板、采购文件 AI 等功能共用。
需在 Flask app 上下文内调用（要读 SysConfig）。

典型用法：
    from services.llm_client import chat, chat_json, test_connection
    text = chat("你是采购文件审阅助手。", "请审阅以下采购需求……")
    data = chat_json("只输出 JSON。", "……")          # 自动解析模型返回的 JSON
    ok, msg = test_connection()                       # 后台「测试连接」用
"""
import json
import os
import re
import subprocess
import tempfile
import time
import requests

from models import db
from models.sys_config import SysConfig

# ── 模型配置：复用「开标看板」已有的键，全系统单一来源 ─────────────────
# 如需让采购文件 AI 与爬虫用不同模型，把下面三个键名改成独立键即可。
DEFAULT_MODEL_API = "http://192.168.1.10:8888/v1/chat/completions"
DEFAULT_MODEL_NAME = "qwen36-apex-mtp-mini"
DEFAULT_API_KEY = "local"

CFG_MODEL_API = "scraper_model_api"
CFG_MODEL_NAME = "scraper_model_name"
CFG_API_KEY = "scraper_api_key"
# HTTP 通道：requests / curl。本机透明代理下部分外网 API（agnesai、Gemini）
# 用 python requests 会挂死，须走 curl 系统栈；由后台「API 管理」启用时自动设置。
CFG_TRANSPORT = "scraper_model_transport"

# ── 嵌入模型配置：独立于 chat，缺省为空=未启用（功能自动降级，不影响现状）──
# 推荐本机 llama.cpp 嵌入服务：llama-server -m bge-m3.gguf --embedding --port 8890
CFG_EMBED_API = "embed_model_api"     # 如 http://127.0.0.1:8890/v1/embeddings
CFG_EMBED_NAME = "embed_model_name"   # 如 bge-m3
CFG_EMBED_KEY = "embed_api_key"


def get_llm_config():
    """读取全局大模型配置，缺省回落本机大模型。须在 app 上下文内调用。"""
    def _val(key, default):
        row = db.session.get(SysConfig, key)
        return row.value if row and row.value else default

    return {
        "api":  _val(CFG_MODEL_API,  DEFAULT_MODEL_API),
        "name": _val(CFG_MODEL_NAME, DEFAULT_MODEL_NAME),
        "key":  _val(CFG_API_KEY,    DEFAULT_API_KEY),
        "transport": _val(CFG_TRANSPORT, "requests"),
    }


def get_embed_config():
    """读取嵌入模型配置；未配置 api 则返回 None（调用方据此降级）。"""
    row = db.session.get(SysConfig, CFG_EMBED_API)
    api = row.value if row and row.value else ""
    if not api:
        return None
    name = db.session.get(SysConfig, CFG_EMBED_NAME)
    key = db.session.get(SysConfig, CFG_EMBED_KEY)
    return {
        "api": api,
        "name": (name.value if name and name.value else "bge-m3"),
        "key": (key.value if key and key.value else "local"),
    }


def embed(texts, *, cfg=None, timeout=120):
    """对一批文本求嵌入向量，返回 [[float,...], ...]。

    走 OpenAI 兼容 /v1/embeddings。未配置嵌入端点或任何异常 → 返回 None，
    由调用方降级（如退回关键词检索）。须在 app 上下文内调用。
    """
    if not texts:
        return []
    cfg = cfg or get_embed_config()
    if not cfg:
        return None
    try:
        r = requests.post(
            cfg["api"],
            headers={"Authorization": f"Bearer {cfg['key']}",
                     "Content-Type": "application/json"},
            json={"model": cfg["name"], "input": list(texts)},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json().get("data") or []
        # 按 index 还原顺序（兼容服务端乱序返回）
        data.sort(key=lambda d: d.get("index", 0))
        vecs = [d.get("embedding") for d in data]
        if len(vecs) != len(texts) or any(not v for v in vecs):
            return None
        return vecs
    except Exception:
        return None


class _CurlResponse:
    """把 curl 结果包成 requests.Response 的最小同构对象。"""

    def __init__(self, status_code, body_text):
        self.status_code = status_code
        self.text = body_text

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if not (200 <= self.status_code < 300):
            raise RuntimeError(f"HTTP {self.status_code}: {self.text[:200]}")


def _post_curl(cfg, payload, timeout):
    """经 curl 子进程 POST（key 走 -K 配置文件，不进 argv）。"""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as pf:
        json.dump(payload, pf, ensure_ascii=False)
        payload_path = pf.name
    with tempfile.NamedTemporaryFile("w", suffix=".cfg", delete=False) as cf:
        cf.write(f'header = "Authorization: Bearer {cfg["key"]}"\n')
        cfg_path = cf.name
    try:
        r = subprocess.run(
            ["curl", "-sS", "-m", str(int(timeout)), "-w", "\n%{http_code}",
             "-H", "Content-Type: application/json",
             "-K", cfg_path, "-d", f"@{payload_path}", cfg["api"]],
            capture_output=True, text=True, timeout=int(timeout) + 10)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or "curl 调用失败").strip()[:200])
        body, _, code = r.stdout.rpartition("\n")
        return _CurlResponse(int(code or 0), body)
    finally:
        for f in (payload_path, cfg_path):
            try:
                os.unlink(f)
            except OSError:
                pass


def _post(cfg, messages, *, temperature, max_tokens, timeout, with_extras,
          response_format=None):
    """单次请求。with_extras=True 时带本机模型专用字段；
    通用在线模型不认这些字段会返回 4xx，由调用方降级重试。"""
    payload = {
        "model": cfg["name"],
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if with_extras:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    if response_format is not None:
        payload["response_format"] = response_format
    if cfg.get("transport") == "curl":
        return _post_curl(cfg, payload, timeout)
    return requests.post(
        cfg["api"],
        headers={
            "Authorization": f"Bearer {cfg['key']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=timeout,
    )


# 已知不支持某 response_format 的 (api|model|type)，命中则直接不发，避免反复 400
_RF_UNSUPPORTED = set()


def _is_local(cfg):
    """自建/本机模型(http://…，如 llama.cpp/局域网 Qwen)才发 chat_template_kwargs；
    公网 https OpenAI 兼容端点(DeepSeek/agnesai/Gemini)不认这些扩展字段。"""
    return str(cfg.get("api", "")).startswith("http://")


def _record_usage(usage_ctx, model, usage):
    """按 usage_ctx 记录账号 token 用量；任何异常都不影响主流程。"""
    if not usage_ctx or not usage:
        return
    try:
        from services.llm_usage import record
        record(usage_ctx.get("username", ""), usage_ctx.get("display_name", ""),
               usage_ctx.get("feature", ""), model, usage,
               agency_code=usage_ctx.get("agency_code", ""))
    except Exception:
        pass


def chat(system, user, *, cfg=None, temperature=0.3, max_tokens=2048,
         timeout=180, retries=2, usage_ctx=None, response_format=None):
    """发一次对话，返回模型文本输出（已去掉 ```代码围栏```）。

    system: 系统提示词（可为空字符串）；user: 用户输入。
    usage_ctx: 形如 {"username","display_name","feature"} 时，自动按账号记录
               本次 token 用量（依赖模型返回的 usage 字段）。
    失败重试 retries 次，全部失败抛 RuntimeError。
    """
    cfg = cfg or get_llm_config()
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    last = None
    with_extras = _is_local(cfg)          # 云端不发扩展字段，避免无谓 400
    cfg_key = f"{cfg.get('api')}|{cfg.get('name')}"
    cur_rf = response_format
    if cur_rf and f"{cfg_key}|{cur_rf.get('type')}" in _RF_UNSUPPORTED:
        cur_rf = None                     # 已知该模型不支持此 response_format
    cur_max_tokens = max_tokens
    for _ in range(retries + 1):
        try:
            r = _post(cfg, messages, temperature=temperature,
                      max_tokens=cur_max_tokens, timeout=timeout,
                      with_extras=with_extras, response_format=cur_rf)
            # 4xx 多因扩展字段或 response_format 不被支持：逐项剥离后立即重试，
            # 并记住该模型不支持的 response_format，后续不再发。
            while r.status_code in (400, 422) and (with_extras or cur_rf is not None):
                if with_extras:
                    with_extras = False
                elif cur_rf is not None:
                    _RF_UNSUPPORTED.add(f"{cfg_key}|{cur_rf.get('type')}")
                    cur_rf = None
                r = _post(cfg, messages, temperature=temperature,
                          max_tokens=cur_max_tokens, timeout=timeout,
                          with_extras=with_extras, response_format=cur_rf)
            r.raise_for_status()
            data = r.json()
            choice = data["choices"][0]
            msg = choice["message"]
            content = (msg.get("content") or "").strip()
            # 思考型模型可能把 max_tokens 全耗在思维链上：正文为空且
            # finish_reason=length。此时 reasoning_content 是截断的思考
            # 过程，不能当正文用；加倍 max_tokens 重试。
            if not content and choice.get("finish_reason") == "length":
                _record_usage(usage_ctx, cfg["name"], data.get("usage"))
                last = RuntimeError(
                    f"输出被 max_tokens={cur_max_tokens} 截断（思考内容耗尽配额）")
                cur_max_tokens *= 2
                continue
            # 部分模型把正文放在 reasoning_content
            if not content and msg.get("reasoning_content"):
                content = msg["reasoning_content"].strip()
            content = re.sub(r"^```(\w+)?\s*|```\s*$", "", content,
                             flags=re.MULTILINE).strip()
            if content:
                _record_usage(usage_ctx, cfg["name"], data.get("usage"))
                return content
            last = RuntimeError("模型返回空内容")
        except Exception as e:
            last = e
            time.sleep(1)
    raise RuntimeError(f"大模型调用失败: {last}")


def chat_json(system, user, *, response_schema=None, **kwargs):
    """同 chat()，但把模型输出解析为 JSON（对象或数组）返回。

    兼容模型先输出分析文字再给 JSON 的情况：从每个 { 或 [ 起尝试
    raw_decode，取首个能完整解析的 JSON。

    response_schema 传入时用 OpenAI response_format=json_schema 强制字段契约
    （Gemini 等会严格遵守；不支持的模型自动降级为普通 JSON + 提示词约束）。"""
    if response_schema is not None and "response_format" not in kwargs:
        kwargs["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": response_schema},
        }
    text = chat(system, user, **kwargs)
    decoder = json.JSONDecoder()
    for m in re.finditer(r"[\{\[]", text):
        try:
            obj, _ = decoder.raw_decode(text, m.start())
        except ValueError:
            continue
        if isinstance(obj, (dict, list)):
            return obj
    raise RuntimeError(f"模型未返回有效 JSON：{text[:200]}")


def test_connection(cfg=None):
    """连通性自检，返回 (ok: bool, message: str)。供后台「测试连接」调用。"""
    try:
        txt = chat("你是一个连接测试助手。", "请只回复两个字：正常",
                   cfg=cfg, temperature=0, max_tokens=32,
                   timeout=30, retries=1)
        return True, f"连接成功，模型返回：{txt[:50]}"
    except Exception as e:
        return False, f"连接失败：{e}"


# ── provider 级模型路由（按任务/成本选模型，不改全局键）─────────────
# 让「投标审查」等功能可在多个已登记的 API 间按角色/成本选择，而不是
# 全系统只能用一个全局模型。典型：长上下文/初筛走便宜模型，★条款交叉核
# 验再上强模型。须在 app 上下文内调用（要读 api_providers 表）。
def cfg_from_provider(ident):
    """从 api_providers 台账取一行，构造 chat() 可用的 cfg。

    ident: provider 的 id(int) 或 name 子串(str，忽略大小写，取 sort 最小的命中行)。
    返回 {"api","name","key","transport","provider_name"}；找不到抛 RuntimeError。
    """
    from models.api_provider import ApiProvider
    q = ApiProvider.query
    row = None
    if isinstance(ident, int) or (isinstance(ident, str) and ident.isdigit()):
        row = db.session.get(ApiProvider, int(ident))
    if row is None and isinstance(ident, str):
        row = (q.filter(ApiProvider.name.ilike(f"%{ident}%"))
                .order_by(ApiProvider.sort).first())
    if row is None:
        raise RuntimeError(f"未找到 API 提供商：{ident}")
    return {
        "api": row.base_url,
        "name": row.model_name,
        "key": row.api_key,
        "transport": row.transport or "requests",
        "provider_name": row.name,
    }


def list_chat_providers():
    """列出所有可用于 chat 的 provider（供路由/评测选择）。返回 [{id,name,model,transport}]。"""
    from models.api_provider import ApiProvider
    rows = (ApiProvider.query.filter(ApiProvider.kind == "chat")
            .order_by(ApiProvider.sort).all())
    return [{"id": r.id, "name": r.name, "model": r.model_name,
             "transport": r.transport or "requests"} for r in rows]
