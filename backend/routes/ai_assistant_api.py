"""耗子 AI 助手 —— 桌面悬浮助手 + 轻量「工具调用」数据查询。

接本机 Qwen（llama-server 8080，固定本地，免费私有）。能力：
  · 普通采购业务问答；
  · 查「当前登录角色权限内」的项目进展并汇总——权限天然来自 session，
    复用 services.project.list_projects 的角色过滤，不会越权。

接口：POST /api/ai-assistant/ask  { question, page } -> { ok, data:{answer, meta?} }

实现：两步式轻量 agent（无需外部 agent 框架）：
  1) 用本地模型判断意图(JSON)：要查数据 / 先问时间范围 / 普通问答；
  2) 若要查 -> 用 session 权限取数 -> 再让模型据真实数据写汇报。
"""
import json
import os
import glob

from flask import Blueprint, request, jsonify, session

import datetime

from werkzeug.utils import secure_filename

from models import db
from models.sys_config import SysConfig
from models.user_balance import UserBalance
from models.llm_usage import LlmUsage
from routes.utils import login_required
from services import llm_client, billing
from services import project as project_svc

# 无限额度（不计费）的人
UNLIMITED_USERS = {"师芮", "黄新博"}


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def _is_unlimited(display_name):
    return display_name in UNLIMITED_USERS


def _get_balance(username, display_name):
    """取/建用户余额（首次建账送 10 元免费额度）。"""
    bal = db.session.execute(
        db.select(UserBalance).filter_by(username=username)
    ).scalar_one_or_none()
    if bal is None:
        bal = UserBalance(username=username, display_name=display_name,
                          balance=10.0, recharged=0.0, spent=0.0, updated_at=_now())
        db.session.add(bal)
        db.session.commit()
    return bal


def _bill_before(username, display_name):
    """调用前余额检查。返回 (ok, err)。"""
    if _is_unlimited(display_name):
        return True, None
    bal = _get_balance(username, display_name)
    if (bal.balance or 0) <= 0:
        return False, "你的 AI 余额已用尽，请点右上角名字充值后再用"
    return True, None


def _max_usage_id():
    row = db.session.execute(db.select(db.func.max(LlmUsage.id))).scalar()
    return row or 0


def _bill_after(username, display_name, since_id):
    """按本次产生的 token 用量扣费（无限用户跳过）。"""
    if _is_unlimited(display_name):
        return
    rows = db.session.execute(
        db.select(LlmUsage).where(LlmUsage.id > since_id, LlmUsage.username == username)
    ).scalars().all()
    tokens = sum((r.total_tokens or 0) for r in rows)
    if tokens <= 0:
        return
    cost = billing.cost_of(tokens)
    bal = _get_balance(username, display_name)
    bal.balance = round((bal.balance or 0) - cost, 6)
    bal.spent = round((bal.spent or 0) + cost, 6)
    bal.updated_at = _now()
    db.session.commit()

bp = Blueprint("ai_assistant", __name__, url_prefix="/api/ai-assistant")


# 模型：耗子用 DeepSeek v4 flash（长上下文，便于吃下内控文件）。
# 默认复用全局大模型配置(SysConfig scraper_*)，可用 assistant_* 键单独覆盖。
def assistant_cfg():
    base = llm_client.get_llm_config()  # 默认 = DeepSeek v4 flash

    def v(key, default):
        row = db.session.get(SysConfig, key)
        return row.value if row and row.value else default

    return {
        "api": v("assistant_model_api", base["api"]),
        "name": v("assistant_model_name", base["name"]),
        "key": v("assistant_model_key", base["key"]),
    }


# 知识库：~/pms/耗子知识/ 下的 docx/txt/md（内控文件、采购经验）注入到回答里
KNOWLEDGE_DIR = os.path.expanduser("~/pms/耗子知识")
_kb_cache = {"text": None, "mtime": -1}


def load_knowledge():
    try:
        os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
        files = sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*")))
        mtime = max((os.path.getmtime(f) for f in files), default=0)
        if _kb_cache["text"] is not None and mtime == _kb_cache["mtime"]:
            return _kb_cache["text"]
        parts = []
        for f in files:
            low = f.lower()
            if low.endswith(".docx"):
                try:
                    import docx
                    parts.append("\n".join(p.text for p in docx.Document(f).paragraphs if p.text.strip()))
                except Exception:
                    pass
            elif low.endswith((".txt", ".md")):
                try:
                    with open(f, encoding="utf-8") as fh:
                        parts.append(fh.read())
                except Exception:
                    pass
        text = "\n\n".join(parts)[:80000]  # DeepSeek 长上下文，限约 8 万字
        _kb_cache.update(text=text, mtime=mtime)
        return text
    except Exception:
        return ""


STATUSES = ["立项", "委托代理", "编制中", "审核中", "已发公告",
            "报名中", "开标", "已定标", "合同签订", "已归档"]

PERSONA = (
    "你是内江市第一人民医院采购部的AI助手，名叫「耗子ai（hxb蒸馏版）」，"
    "熟悉政府采购与本单位采购内控流程（立项→委托代理→编制→审核→公告→报名→开标→定标→合同→归档）。"
    "用简体中文，简明扼要，能分点就分点。"
)


def persona_with_kb():
    kb = load_knowledge()
    if kb:
        return (PERSONA + "\n\n【本单位采购内控文件 / 采购经验（回答须严格依据以下内容，"
                "涉及金额档次、采购方式选择、流程时限等以此为准；无依据时如实说明）】：\n" + kb)
    return PERSONA


# ────────────────────────── 工具：查项目进展（权限来自 session）──────────────────────────
def _tool_project_progress(args):
    """按当前登录用户的角色权限查可见项目，过滤后返回精简结构供模型汇总。"""
    role = session.get("role", "")
    projects = project_svc.list_projects(
        role,
        agency_code=session.get("agency_code", ""),
        officer=session.get("display_name", ""),
    )
    tf = (args.get("time_from") or "").strip()
    tt = (args.get("time_to") or "").strip()
    status = (args.get("status") or "").strip()
    kw = (args.get("keyword") or "").strip()

    def in_range(p):
        d = (p.get("updated_at") or p.get("created_at") or "")[:10]
        if not d:
            return not (tf or tt)
        if tf and d < tf:
            return False
        if tt and d > tt:
            return False
        return True

    rows, by_status = [], {}
    for p in projects:
        if p.get("is_draft") or p.get("status") == "草稿":
            continue
        if not in_range(p):
            continue
        if status == "未归档":
            if p.get("status") == "已归档":
                continue
        elif status and p.get("status") != status:
            continue
        if kw and kw not in (p.get("name") or ""):
            continue
        amount = p.get("amount")
        rows.append({
            "项目": p.get("name", ""),
            "编号": p.get("number", ""),
            "当前状态": p.get("status", ""),
            "经办人": p.get("officer", ""),
            "代理机构": p.get("agency_name", ""),
            "金额万元": round(amount / 10000, 2) if amount else "",
            "采购方式": p.get("method", ""),
            "更新时间": (p.get("updated_at") or "")[:16],
        })
        s = p.get("status") or "未知"
        by_status[s] = by_status.get(s, 0) + 1

    rows.sort(key=lambda r: r["更新时间"], reverse=True)
    return {
        "总数": len(rows),
        "按状态统计": by_status,
        "项目明细": rows[:80],
        "口径": f"当前账号({session.get('display_name', '')}/{role or '未知角色'})权限可见的项目",
    }


TOOLS_DESC = (
    "可用工具 query_project_progress：查询当前用户权限内的项目及进展。"
    "参数对象 args 含：time_from(起YYYY-MM-DD,可空)、time_to(止YYYY-MM-DD,可空)、"
    f"status(项目状态,可空,取值之一:{'/'.join(STATUSES)}；另可填\"未归档\"表示排除已归档的全部在办项目)、"
    "keyword(项目名关键词,可空)。所有参数留空即返回该用户全部可见项目(已按更新时间倒序)。"
)

INTENT_SYS = (
    PERSONA + "\n判断用户这句话的意图。" + TOOLS_DESC +
    "\n严格只输出一个 JSON 对象，二选一：\n"
    '1) 凡是问项目进展/最近情况/某状态或某类项目/统计/列表/“未归档/在办/进行中的项目”等，'
    '一律用 -> {"action":"tool","args":{"time_from":"","time_to":"","status":"","keyword":""}}；'
    '绝不要因为用户没说时间范围就拒答或反问，时间留空即查全部（结果已按更新时间倒序，天然就是“最近”）。'
    '按语义填 args：说“未归档/在办/没归档/进行中/还没归档”→ status="未归档"；'
    f'说到具体状态(如{STATUSES[0]}、{STATUSES[5]}、{STATUSES[-1]}等)→ 填对应 status；'
    '提到某项目名/关键词 → 填 keyword；明确说了具体时间段才填 time_from/time_to。\n'
    '2) 与项目数据无关的纯业务/制度咨询(如“15万走什么采购方式”“某流程怎么走”) -> {"action":"answer"}\n'
    "只输出 JSON，不要任何额外文字。已知今天日期由系统注入。"
)


@bp.route("/ask", methods=["POST"])
@login_required
def ask():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    page = (data.get("page") or "").strip()
    if not question:
        return jsonify({"ok": False, "error": "问题不能为空"}), 400

    today = datetime.date.today().isoformat()
    username = session.get("user", "")
    display_name = session.get("display_name", "")
    usage_ctx = {"username": username, "display_name": display_name, "feature": "耗子助手"}

    # 计费：调用前查余额（无限用户免）
    ok, err = _bill_before(username, display_name)
    if not ok:
        return jsonify({"ok": False, "error": err, "need_recharge": True}), 402
    since_id = _max_usage_id()

    def _done(payload):
        _bill_after(username, display_name, since_id)
        return jsonify({"ok": True, "data": payload})

    # 第一步：意图判断（要数据 / 先问 / 普通问答）
    try:
        intent = llm_client.chat_json(
            INTENT_SYS, f"今天是{today}。用户：{question}",
            cfg=assistant_cfg(), temperature=0, max_tokens=400, timeout=60,
        )
    except Exception:
        intent = {"action": "answer"}
    action = intent.get("action") if isinstance(intent, dict) else "answer"

    # 分支2：反问时间范围
    if action == "ask":
        q = intent.get("question") or "您想看哪个时间范围的项目进展？例如本月、今年，或具体起止日期。"
        return _done({"answer": q, "meta": {"mode": "ask"}})

    # 分支1：查数据 -> 汇总
    if action == "tool":
        try:
            tool_data = _tool_project_progress(intent.get("args") or {})
        except Exception as e:
            return jsonify({"ok": False, "error": f"查询项目数据失败：{e}"}), 500
        if tool_data["总数"] == 0:
            return _done({
                "answer": "在你权限可见范围、且符合条件的项目里没找到记录。可以换个时间范围或状态再试。",
                "meta": {"mode": "tool", "queried": 0}})
        sys2 = (
            PERSONA +
            "\n下面是系统按当前用户权限查到的真实项目数据(JSON)。请据此写一份**项目进展汇报**："
            "①一句总览（共几个、各状态分布）；②分点列关键项目（项目名—当前状态—经办人—更新时间）；"
            "③点出需关注的（如长期停留某状态、临近节点）。只基于给定数据，不得编造法规或数字。"
        )
        user2 = f"用户的问题：{question}\n项目数据：{json.dumps(tool_data, ensure_ascii=False)}"
        try:
            answer = llm_client.chat(
                sys2, user2, cfg=assistant_cfg(), temperature=0.3,
                max_tokens=1500, timeout=180, usage_ctx=usage_ctx,
            )
        except Exception as e:
            return jsonify({"ok": False, "error": f"汇总失败：{e}"}), 500
        return _done({"answer": answer, "meta": {"mode": "tool", "queried": tool_data["总数"]}})

    # 分支3：普通问答（注入内控文件/经验知识库；用户问"15万走什么方式"等据此回答）
    sys_prompt = persona_with_kb() + (f"\n（当前用户正在「{page}」页面操作。）" if page else "")
    try:
        answer = llm_client.chat(
            sys_prompt, question, cfg=assistant_cfg(), temperature=0.4,
            max_tokens=1500, timeout=120, usage_ctx=usage_ctx,
        )
        return _done({"answer": answer, "meta": {"mode": "chat"}})
    except Exception as e:
        return jsonify({"ok": False, "error": f"模型调用失败：{e}"}), 500


# ── 账户：余额 / 用量（点右上角名字弹出）──────────────────────────
@bp.route("/account", methods=["GET"])
@login_required
def account():
    username = session.get("user", "")
    display_name = session.get("display_name", "")
    bal = _get_balance(username, display_name)
    rows = db.session.execute(
        db.select(LlmUsage).where(LlmUsage.username == username)
        .order_by(LlmUsage.id.desc()).limit(10)
    ).scalars().all()
    recent = [{"feature": r.feature, "model": r.model, "tokens": r.total_tokens,
               "cost": round(billing.cost_of(r.total_tokens), 4), "at": r.created_at}
              for r in rows]
    return jsonify({"ok": True, "data": {
        "display_name": display_name, "unlimited": _is_unlimited(display_name),
        "balance": round(bal.balance or 0, 4), "recharged": round(bal.recharged or 0, 2),
        "spent": round(bal.spent or 0, 4), "price_per_million": billing.get_price(),
        "recent": recent}})


@bp.route("/recharge", methods=["POST"])
@login_required
def recharge():
    # 充值入口占位，后续接支付
    return jsonify({"ok": False, "error": "充值功能开发中，请联系管理员开通额度。"})


# ── 知识库：上传/列出/删除（内控文件、采购经验）──────────────────
def _kb_manage_ok():
    from services.permission import is_admin_user
    return _is_unlimited(session.get("display_name", "")) or is_admin_user(session.get("user", ""))


def _kb_safe_name(fn):
    name = os.path.basename(fn or "").replace("/", "_").replace("\\", "_").strip()
    return name or f"kb_{int(__import__('time').time())}.txt"


@bp.route("/knowledge", methods=["GET"])
@login_required
def knowledge_list():
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    files = [{"name": os.path.basename(f), "size": os.path.getsize(f)}
             for f in sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*")))]
    return jsonify({"ok": True, "data": {
        "files": files, "chars": len(load_knowledge()), "can_manage": _kb_manage_ok()}})


@bp.route("/knowledge", methods=["POST"])
@login_required
def knowledge_upload():
    if not _kb_manage_ok():
        return jsonify({"ok": False, "error": "仅管理员/师芮/黄新博可维护知识库"}), 403
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "未选择文件"}), 400
    name = _kb_safe_name(file.filename)
    if not name.lower().endswith((".docx", ".txt", ".md")):
        return jsonify({"ok": False, "error": "只支持 docx / txt / md"}), 400
    os.makedirs(KNOWLEDGE_DIR, exist_ok=True)
    file.save(os.path.join(KNOWLEDGE_DIR, name))
    _kb_cache["mtime"] = -1  # 失效缓存，下次问答重新读取
    return jsonify({"ok": True, "data": {"name": name, "chars": len(load_knowledge())}})


@bp.route("/knowledge/<path:name>", methods=["DELETE"])
@login_required
def knowledge_delete(name):
    if not _kb_manage_ok():
        return jsonify({"ok": False, "error": "无权限"}), 403
    p = os.path.join(KNOWLEDGE_DIR, _kb_safe_name(name))
    if os.path.exists(p):
        os.remove(p)
        _kb_cache["mtime"] = -1
    return jsonify({"ok": True})
