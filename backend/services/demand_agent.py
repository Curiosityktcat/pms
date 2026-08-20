# -*- coding: utf-8 -*-
"""采购需求 Agent：读上传的资料，把能认出来的信息填进需求表。

黄新博 2026-08-19 ⑩ 的第 2 条：「目前无法上传文件让 agent 去填写采购需求，
可以上传一些文件，然后通过对话的方式让 Agent 干活，填写采购需求。」

三条硬规矩，来自 procurement-doc-templates（pdt）第二条和这套系统的教训：

  1. **金额、编号、日期、单位名称不让模型写。** 这些是要盖章对外发的，
     让模型「生成」一个金额迟早出事故。Agent 只从原文里**摘**，摘不到就留空，
     绝不推断、不补全、不换算。
  2. **只提建议，不直接落库。** 返回的是「建议值 + 依据原文」，
     人看过、点了采纳才写进去。
  3. **锁定的字段不碰。** 字段字典里被条件锁死的（比如政采的组织形式只能是
     分散采购），Agent 连建议都不给——那是规则定死的，不是它该管的。
"""
import io
import json
import re

# 只让 Agent 碰这些字段。选项类的会限定在字典给的选项里。
# 金额/编号/日期这类不在列——它们要么来自立项，要么必须人填。
AGENT_FIELDS = [
    ("项目概况", "text", "项目要买什么、用来干什么，两三句话"),
    ("相关产业发展情况", "text", "第二部分需求调查用"),
    ("市场供给情况", "text", "第二部分需求调查用"),
    ("历史成交情况", "text", "同类项目历史成交信息"),
    ("后续采购情况", "text", "运维、升级、备品备件、耗材等后续采购"),
    ("其他相关情况", "text", "第二部分其他"),
    ("合同履行期限", "text", "如「2026年1月起；2026年12月止」，原文没有就留空"),
    ("合同履约地点", "text", ""),
    ("合同支付约定", "text", "付款方式与比例"),
    ("验收交付标准和方法", "text", ""),
    ("质量保修范围和保修期", "text", ""),
    ("履约验收程序", "text", ""),
    ("履约验收时间", "text", ""),
]

# 分包里的字段，Agent 也能给建议（按包）
AGENT_PACKAGE_FIELDS = [
    ("技术要求", "参数、指标、配置。原文里如果是表格，按「参数项/技术要求」两列整理"),
    ("商务要求", "交货期、质保、售后、培训这类"),
    ("特殊资格要求", "结合标的的资质要求，如医疗器械经营许可"),
]

SYSTEM = """你是医院采购部的需求编制助手。你的任务是从用户给的资料里提取信息，
填进《采购需求表》的相应字段。

铁律（违反就是事故）：
1. 结构可以重组：允许拆条款、归类到技术/商务、整理成表格和重新编号。
2. 事实必须原样：参数值、金额、编号、日期、单位名称只能照抄原文；原文没有就留空。
3. 摘不准就留空。留空是安全的，编一个是危险的——这些文件要盖章对外发。
4. 每个字段都要给出 evidence：原文里支持这个填法的那一句（照抄，不超过 80 字）。
   给不出 evidence 的字段，就不要填。

只输出 JSON，不要任何解释文字。格式：
{"fields": {"字段名": {"value": "值", "evidence": "原文依据"}},
 "packages": [{"技术要求": {"value": "...", "evidence": "..."}}],
 "notes": ["你拿不准的地方，用中文说明"]}"""


def _clean_json(text):
    """模型有时会带围栏或前后废话，尽力抠出 JSON。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i >= 0 and j > i:
        t = t[i:j + 1]
    try:
        return json.loads(t)
    except Exception:                                        # noqa: BLE001
        return None


MAX_CHARS_PER_FILE = 20000
PROMPT_CHAR_LIMIT = 4000


def _bounded_user(system, user):
    """保证单次调用的 system+user 不超过 4000 字，结尾的当前问题优先保留。"""
    room = max(0, PROMPT_CHAR_LIMIT - len(system))
    if len(user) <= room:
        return user
    head = min(700, room // 3)
    return user[:head] + "\n……（中间资料已截短）……\n" + user[-max(0, room - head - 18):]


def _plain_text(path):
    """纯文本自己读——公共的 extract_file_text 只管 Office 和图片，不认 .txt。
    它是给合同附件识别写的，不该为了这个改它的口径。"""
    for enc in ("utf-8", "gb18030", "utf-16"):
        try:
            with io.open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    with io.open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def read_files(paths):
    """把上传的资料读成文字。读不了的记下来告诉人，不静默跳过。"""
    import os as _os
    from services.rdweb_autofill import extract_file_text
    chunks, failed = [], []
    for name, path in paths:
        try:
            if _os.path.splitext(path)[1].lower() in (".txt", ".md", ".csv"):
                txt = _plain_text(path)
            else:
                txt = extract_file_text(path)
            txt = (txt or "").strip()
            if len(txt) < 10:
                failed.append(f"{name}：里面没读到文字")
                continue
            chunks.append(f"【{name}】\n{txt[:MAX_CHARS_PER_FILE]}")
        except Exception as e:                               # noqa: BLE001
            failed.append(f"{name}：{str(e)[:80]}")
    return "\n\n".join(chunks), failed


def _technical_suggestion(material, *, usage_ctx=None, total_score=None,
                          tri_ratio=None):
    """技术资料走 A-D 短流程，模型不再把全文抄进 JSON。"""
    from services import demand_agent_steps as steps
    rows = steps.parse_clauses(material)
    if not rows:
        return None
    # 分值设置文件与参数文件一起上传时，比例只从原文数字读取，不让模型计算。
    if tri_ratio is None:
        gm = re.search(r"一般条款得分[^\n]{0,120}?[×xX]\s*([0-9]+(?:\.[0-9]+)?)\s*分", material)
        tm = re.search(r"[“\"']?▲[”\"']?条款得分[^\n]{0,120}?[×xX]?\s*([0-9]+(?:\.[0-9]+)?)\s*分", material)
        if gm and tm:
            general_score, tri_score = float(gm.group(1)), float(tm.group(1))
            score_sum = general_score + tri_score
            if score_sum > 0:
                total_score, tri_ratio = score_sum, tri_score / score_sum
    result = steps.run(material, total_score=total_score, tri_ratio=tri_ratio,
                       usage_ctx=usage_ctx)
    table = result["D_technical_table"]
    value = json.dumps(table["blocks"], ensure_ascii=False)
    groups = []
    for row in rows:
        if row.get("group") and row["group"] not in groups:
            groups.append(row["group"])
    first_no, last_no = rows[0]["no"], rows[-1]["no"]
    evidence = f"技术条款 {first_no} 至 {last_no}，共拆成 {len(rows)} 行"
    notes = []
    counted = result["C_count_scores"]
    notes.append(
        f"计数：一般{counted['general']}条、▲{counted['tri']}条；"
        f"分值：一般{counted['general_score']}分、▲{counted['tri_score']}分"
    )
    if groups:
        notes.append(f"识别到{len(groups)}个设备分组：" + "、".join(groups))
    basic = result.get("F_basic_information")
    fields = {}
    if basic and basic.get("项目概况"):
        fields["项目概况"] = {
            "value": basic["项目概况"],
            "evidence": basic["项目概况"][:120],
        }
    return {"fields": fields,
            "packages": [{"技术要求": {"value": value, "evidence": evidence}}],
            "notes": notes, "steps": result}


def _focused_text_suggestion(material, material_kind, *, usage_ctx=None):
    """非技术资料也按 E/F 分开做，避免一次让模型填 13 个无关字段。"""
    from services import demand_agent_steps as steps
    fields, packages, notes, artifacts = {}, [], [], {}
    if material_kind == "basic":
        basic = steps.basic_information(material, usage_ctx=usage_ctx)
        artifacts["F_basic_information"] = basic
        if basic.get("项目概况"):
            fields["项目概况"] = {"value": basic["项目概况"],
                                  "evidence": basic["项目概况"][:120]}
        if basic.get("packages"):
            notes.append("识别到%d个采购包：%s" % (
                basic["包数"], "、".join(
                    f"{x['包名']}预算{x['预算金额']}" for x in basic["packages"])))

    if material_kind == "business":
        business = steps.business_requirements(material, usage_ctx=usage_ctx)
        artifacts["E_business"] = business
        if business.get("blocks"):
            packages.append({"商务要求": {
                "value": json.dumps(business["blocks"], ensure_ascii=False),
                "evidence": "、".join(business["sections"].keys())[:120],
            }})
    if not fields and not packages and not notes:
        return None
    return {"fields": fields, "packages": packages, "notes": notes,
            "steps": artifacts}


def suggest(material, instruction="", locked_names=(), usage_ctx=None,
            total_score=None, tri_ratio=None):
    """让模型给建议。返回 {"fields":{...}, "packages":[...], "notes":[...]}。

    locked_names 是字段字典判定为锁定的字段——Agent 连建议都不给。
    """
    initial_facts = []
    if total_score is not None:
        initial_facts.append({"key": "total_score", "value": total_score})
    if tri_ratio is not None:
        initial_facts.append({"key": "tri_ratio", "value": tri_ratio})
    # 一次性入口也复用同一条对话主干，避免它继续按旧关键词把任意编号资料
    # 当技术参数。这里只是不落 facts；持久对话入口才负责保存确认结果。
    return converse([], instruction, material=material, locked_names=locked_names,
                    usage_ctx=usage_ctx, facts=initial_facts,
                    filenames=["上传资料"])


# ══════════════════════════════════════════════════════════════════
# 对话模式（黄新博 2026-08-20：做成像微信一样，有消息记录、能传文件、
# 直接用大白话告诉它怎么干）
# ══════════════════════════════════════════════════════════════════

CHAT_SYSTEM = """你是医院采购部的需求编制助手，正在和采购部经办人对话，
帮他把《采购需求表》填起来。

对话时：
- 说人话，简短。不要复述他说过的话，不要写「好的，我明白了」这类废话。
- 他传资料给你，你就读了告诉他能填哪些、填了什么。
- 他让你改某一项，你就改那一项，不要顺手动别的。
- 你拿不准的、资料里没有的，**直接说没有**，不要编。

铁律（违反就是事故）：
1. 可以重组结构：拆条款、归类、制表和编号都可以；不要把整篇原文塞进一个字段。
2. 参数值、金额、编号、日期、单位名称必须照抄原文，原文没有的不许补。
3. 每条建议都要带 evidence（原文依据，照抄，不超过 80 字）。给不出依据就别填。
4. 这些文件要盖章对外发——留空是安全的，编一个是危险的。

回复格式：先写给人看的话（纯文本，别用 markdown 标题），
如果这一轮有可填的内容，再另起一行输出一个 JSON 块，用 ```json 围起来：
```json
{"fields": {"字段名": {"value": "值", "evidence": "原文依据"}},
 "packages": [{"技术要求": {"value": "...", "evidence": "..."}}]}
```
没有可填内容时**不要输出 JSON 块**，只说话就行。"""

INTENT_SYSTEM = """你只判断采购需求对话中经办人这一轮的意图，并把他明确回答的事实对到 key。
意图只能是 answer（回答待确认问题）、material（处理新资料）、edit（修改一项）、ask（普通提问）。
经办人的明示永远优先于资料外观；他说“这是商务要求”就必须记录为 business。
经办人本轮如果说明资料类型，必须输出一条 material_kind:<本轮文件名> 的 answer：
- “这是技术参数/技术要求”取 technical；“这是商务要求/商务条款”取 business；
- “这是评审办法/评分办法/分值设置”取 scoring；“这是项目基本情况/基本信息”取 basic；
- “这是混合资料”取 mixed；明确属于其余资料取 other。
只有一个本轮文件时，他说“这份”而没有说文件名，也要对到该文件；有多个本轮文件且没有指明
哪一份时，不得猜文件。只说“不是技术参数”等排除结论时，不得仍填 technical，也不得猜成其他类型。
只输出JSON：{"intent":"material","answers":[{"key":"事实key","value":"值"}],"instruction":"短说明"}。
只能记录经办人明确说过的答案，不得替他猜。"""

def _question(key, ask, why, kind="text", options=None, *, suggestion="",
              suggestion_reason="", confidence="low"):
    """问题统一从这里生成，避免漏掉 why 或前端需要的字段。"""
    if not why:
        raise ValueError("待确认问题必须说明为什么要问")
    return {"key": key, "ask": ask, "why": why, "kind": kind,
            "options": list(options or []), "suggestion": suggestion,
            "suggestion_reason": suggestion_reason,
            "confidence": confidence if confidence in ("high", "medium", "low") else "low"}


def _confidence_label(value):
    """模型给数值把握，界面只展示三档，避免把小数伪装成精确概率。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if number >= 0.85:
        return "high"
    if number >= 0.75:
        return "medium"
    return "low"


def _material_kind_directive(user_text, filenames):
    """兜住经办人的资料类型明示；模型负责理解，代码负责不让明示被反悔。

    这里只认采购业务里非常明确的说法。含糊表达仍交给意图模型，避免关键词
    猜资料类型的旧问题借尸还魂。
    """
    text = (user_text or "").strip()
    names = [str(x) for x in filenames or () if str(x)]
    if not text or not names:
        return [], [], set()
    excluded_technical = bool(re.search(r"(?:不是|不属于|别当(?:成|作)?|不要当(?:成|作)?)\s*技术(?:参数|要求)?", text))
    positive_text = re.sub(
        r"(?:不是|不属于|别当(?:成|作)?|不要当(?:成|作)?)\s*技术(?:参数|要求)?", "", text)
    patterns = (
        ("business", r"商务(?:要求|条款|资料)"),
        ("scoring", r"(?:评审|评分)办法|分值设置|评审标准"),
        ("basic", r"项目基本(?:情况|信息)|基本信息"),
        ("mixed", r"混合资料"),
        ("technical", r"技术(?:参数|要求)"),
        ("other", r"其他资料"),
    )
    kind = next((value for value, pattern in patterns
                 if re.search(pattern, positive_text)), None)
    matched_names = []
    for name in names:
        stem = re.sub(r"\.[^.]+$", "", name)
        if name in text or (len(stem) >= 2 and stem in text):
            matched_names.append(name)
    target = matched_names[0] if len(matched_names) == 1 else None
    if target is None and len(names) == 1:
        target = names[0]

    if kind and target:
        return ([{"key": f"material_kind:{target}", "value": kind}], [], set())
    if kind and not target:
        options = [{"label": name,
                    "value": {"key": f"material_kind:{name}", "value": kind}}
                   for name in names]
        question = _question(
            "material_kind_target", f"你说的“{_kind_label(kind)}”是指哪一份资料？",
            "本轮有多份资料；不先对准文件会把另一份资料走进错误的处理步骤",
            "choice", options,
            suggestion_reason="你已经明确了资料类型，但没有指明文件；仅凭文件外观替你对号容易串件。",
            confidence="low")
        return [], [question], {f"material_kind:{name}" for name in names}
    if excluded_technical:
        targets = [target] if target else names
        shown = f"“{targets[0]}”" if len(targets) == 1 else "你提到的资料"
        question = _question(
            f"material_kind:{targets[0]}" if len(targets) == 1 else "material_kind_target",
            f"已确认{shown}不是技术参数，那它是什么资料？",
            "排除技术参数后仍需确定走商务归类、评审分值读取还是基本信息提取，不能静默猜一种",
            "choice", [
                {"label": "商务要求", "value": "business"},
                {"label": "评审办法/分值", "value": "scoring"},
                {"label": "项目基本信息", "value": "basic"},
                {"label": "混合资料", "value": "mixed"},
                {"label": "其他资料", "value": "other"},
            ], suggestion_reason="你只排除了“技术参数”，现有原话不足以在其余资料类型中继续代选。",
            confidence="low")
        return [], [question], {f"material_kind:{name}" for name in targets}
    return [], [], set()


def _kind_label(kind):
    return {"technical": "技术参数", "business": "商务要求", "scoring": "评审办法",
            "basic": "项目基本信息", "mixed": "混合资料", "other": "其他资料"}.get(kind, kind)


def _material_parts(material, filenames=()):
    """按 read_files 的附件标题拆开；旧消息没有文件名时仍作为一份资料处理。"""
    matches = list(re.finditer(r"(?m)^【([^\n】]+)】\s*$", material or ""))
    if matches:
        out = []
        for i, match in enumerate(matches):
            end = matches[i + 1].start() if i + 1 < len(matches) else len(material)
            out.append((match.group(1).strip(), material[match.end():end].strip()))
        return [(name, text) for name, text in out if text]
    name = next(iter(filenames or ()), "本轮资料")
    return [(name, (material or "").strip())] if (material or "").strip() else []


def _fact_values(facts):
    out = {}
    for fact in facts or []:
        if isinstance(fact, dict) and fact.get("key"):
            out[str(fact["key"])] = fact.get("value")
    return out


def _conversation_intent(history, user_text, material, pending, filenames, facts,
                         *, usage_ctx=None):
    """只用短上下文判意图和回答；按钮回答带 key 时不再让模型二次猜。"""
    batch = re.match(r"^【批量采纳建议】(.*)$", (user_text or "").strip(), re.S)
    if batch:
        try:
            items = json.loads(batch.group(1).strip())
        except Exception:                                    # noqa: BLE001
            items = []
        answers = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not item.get("key"):
                continue
            answers.append({"key": str(item["key"]), "value": item.get("value"),
                            "evidence": "经办人本轮采纳 agent 建议：" +
                                        str(item.get("reason") or "")[:360]})
        return {"intent": "answer", "answers": answers, "instruction": ""}

    marker = re.match(r"^【(回答|采纳建议):([^】]+)】(.*)$", (user_text or "").strip(), re.S)
    if marker:
        raw = marker.group(3).strip()
        try:
            value = json.loads(raw)
        except Exception:                                    # noqa: BLE001
            value = raw
        evidence = "经办人本轮选择"
        if marker.group(1) == "采纳建议" and isinstance(value, dict):
            reason = str(value.get("reason") or "")[:360]
            value = value.get("value")
            evidence = "经办人本轮采纳 agent 建议：" + reason
        return {"intent": "answer",
                "answers": [{"key": marker.group(2).strip(), "value": value,
                             "evidence": evidence}],
                "instruction": ""}

    recent = []
    for item in history[-6:]:
        text = (item.get("text") or "").strip()
        if text:
            recent.append(("经办人" if item.get("role") == "user" else "助手") + "：" + text[:300])
    pending_lines = [
        f"{x.get('key')}：{x.get('ask')}；选项={json.dumps(x.get('options') or [], ensure_ascii=False)}"
        for x in (pending or [])[:6]
    ]
    file_lines = [f"material_kind:{x}" for x in filenames]
    user = "\n".join([
        "最近对话：", *recent,
        "待回答事实：", *(pending_lines or ["（无）"]),
        "本次已确认事实：", json.dumps(_fact_values(facts), ensure_ascii=False)[:800],
        "本轮资料事实key：", *(file_lines or ["（无新资料）"]),
        "本轮资料前600字：", (material or "")[:600],
        "经办人本轮原话：", user_text or "（只传了资料）",
    ])
    from services import demand_agent_steps as steps
    data, _chars = steps._call_json(INTENT_SYSTEM, user, usage_ctx=usage_ctx)  # noqa: SLF001
    intent = str(data.get("intent") or ("material" if material else "ask"))
    if intent not in {"answer", "material", "edit", "ask"}:
        intent = "material" if material else "ask"
    answers = []
    for item in data.get("answers") or []:
        if isinstance(item, dict) and item.get("key") and "value" in item:
            answers.append({"key": str(item["key"]), "value": item["value"],
                            "evidence": "经办人本轮回答"})
    return {"intent": intent, "answers": answers,
            "instruction": str(data.get("instruction") or "")[:200]}


def _pending_from_history(history):
    for item in reversed(history or []):
        suggestions = item.get("suggestions") or {}
        if isinstance(suggestions, dict) and suggestions.get("questions"):
            return suggestions["questions"]
    return []


def _normalise_fact_value(key, value):
    """只做格式归一，不改事实；数值解析失败就保留原回答，后面继续问清。"""
    if key.startswith("material_kind:"):
        kinds = {"技术参数": "technical", "技术": "technical",
                 "商务要求": "business", "商务": "business",
                 "评审办法": "scoring", "分值设置": "scoring",
                 "项目基本信息": "basic", "基本信息": "basic",
                 "混合资料": "mixed", "其他资料": "other"}
        return kinds.get(str(value).strip(), value)
    if key == "total_score":
        match = re.search(r"[0-9]+(?:\.[0-9]+)?", str(value))
        return float(match.group()) if match else value
    if key == "whole_tops" and isinstance(value, str):
        if value in ("leaf", "逐条", "逐条计数", "不是"):
            return []
        return re.findall(r"\d+(?:\.\d+)*", value)
    if key == "tri_ratio":
        numbers = [float(x) for x in re.findall(r"[0-9]+(?:\.[0-9]+)?", str(value))]
        if len(numbers) >= 2 and sum(numbers[:2]) > 0:
            return numbers[1] / sum(numbers[:2])
        if numbers:
            return numbers[0] / 100 if numbers[0] > 1 else numbers[0]
    return value


def _whole_top_quotes(rows, selected):
    """建议理由只摘解析行里的原文，不让模型把概括伪装成引用。"""
    selected = {str(x) for x in selected or ()}
    quotes = []
    for row in rows or []:
        no = str(row.get("no") or "")
        group = str(row.get("group") or "")
        matched = False
        for ident in selected:
            wanted_group, top = ident.rsplit("|", 1) if "|" in ident else ("", ident)
            if (not wanted_group or wanted_group == group) and (no == top or no.startswith(top + ".")):
                matched = True
                break
        if not matched or no in {x.rsplit("|", 1)[-1] for x in selected}:
            continue
        source = str(row.get("text") or row.get("raw") or "").strip()
        if source and source not in quotes:
            quotes.append(source[:36])
        if len(quotes) >= 4:
            break
    return quotes


def _split_reply(text):
    """把模型回复拆成「给人看的话」和「结构化建议」。

    模型不一定老实加 ```json 围栏——实测经常直接吐裸 JSON。
    所以从「第一个带 fields/packages 的大括号」开始，用括号配对找到它的结尾，
    比正则可靠（JSON 里嵌套花括号，正则的非贪婪匹配会截断）。
    """
    t = (text or "").strip()
    data, say = None, t

    m = re.search(r"```json\s*(\{.*?\})\s*```", t, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            say = (t[:m.start()] + t[m.end():]).strip()
        except Exception:                                    # noqa: BLE001
            data = None

    if data is None:
        # 裸 JSON：找到第一个像建议块的 {，然后括号配对找结尾
        for mm in re.finditer(r"\{", t):
            start = mm.start()
            tail = t[start:start + 200]
            if '"fields"' not in tail and '"packages"' not in tail:
                continue
            depth, end, instr, esc = 0, -1, False, False
            for i, ch in enumerate(t[start:], start):
                if instr:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        instr = False
                    continue
                if ch == '"':
                    instr = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > start:
                try:
                    data = json.loads(t[start:end])
                    say = (t[:start] + t[end:]).strip()
                    break
                except Exception:                            # noqa: BLE001
                    continue

    say = re.sub(r"```(?:json)?|```", "", say).strip()
    return say, data


def converse(history, user_text, material="", locked_names=(), usage_ctx=None,
             facts=(), filenames=(), force_questions=()):
    """对话一轮。

    history: [{"role": "user"/"agent", "text": ...}, ...]，按时间正序
    material: 这一轮新传的文件读出来的文字（可空）
    返回 {"say": 给人看的话, "fields": {...}, "packages": [...], "notes": [...]}
    """
    from services import demand_agent_steps as steps
    from services import llm_client

    pending = _pending_from_history(history)
    intent = _conversation_intent(history, user_text, material, pending, filenames, facts,
                                  usage_ctx=usage_ctx)
    direct_answers, directive_questions, blocked_kind_keys = _material_kind_directive(
        user_text, filenames)
    direct_keys = {x["key"] for x in direct_answers}
    intent["answers"] = [x for x in intent["answers"]
                         if x["key"] not in direct_keys and x["key"] not in blocked_kind_keys]
    intent["answers"].extend({**x, "evidence": "经办人本轮选择"} for x in direct_answers)
    fact_updates = []
    allowed_answer_keys = {
        "whole_tops", "total_score", "tri_ratio", "count_rule", "count_rule_detail",
        "package_plan", "price_deduct", "material_kind_target",
        *(str(x.get("key")) for x in pending if x.get("key")),
        *(f"material_kind:{name}" for name in filenames),
    }
    for answer in intent["answers"]:
        key = answer["key"]
        if key not in allowed_answer_keys:
            continue
        if key == "material_kind_target":
            target = answer.get("value")
            if not isinstance(target, dict) or not str(target.get("key") or "").startswith(
                    "material_kind:"):
                # 多附件时自由文本仍交给意图模型对回具体事实；只给了文件名时还缺
                # 资料类型，不能凭空落一个半成品事实。
                continue
            key = str(target["key"])
            answer = {**answer, "value": target.get("value")}
        fact_updates.append({
            "key": key, "value": _normalise_fact_value(key, answer["value"]),
            "source": "user", "evidence": answer.get("evidence") or "经办人本轮回答",
        })
    effective = _fact_values(facts)
    effective.update({x["key"]: x["value"] for x in fact_updates})
    forced = set(force_questions or ())

    # 撤销事实后没有新附件，也要从最近一次资料重算；普通追问则只把历史资料
    # 放进 prompt，不擅自重新生成建议。
    work_material = material
    work_filenames = list(filenames or ())
    if not work_material and "撤销" in (user_text or ""):
        previous_materials = []
        for item in history or []:
            old_material = (item.get("material") or "").strip()
            if old_material and old_material not in previous_materials:
                previous_materials.append(old_material)
        # 撤销的事实可能来自更早的附件，不能只拿最后一份资料重算；保留标题后
        # 合并历史资料，后面的资料类型事实仍会阻止它们被走错步骤。
        work_material = "\n\n".join(previous_materials[-8:])
    elif not work_material and intent["intent"] == "answer":
        for item in reversed(history or []):
            if (item.get("material") or "").strip():
                work_material = item["material"]
                work_filenames = [f.get("name") for f in item.get("files") or [] if f.get("name")]
                break

    questions, notes, artifacts = list(directive_questions), [], {}
    fields, packages = {}, []
    processed = []
    parts = _material_parts(work_material, work_filenames)

    for filename, text in parts:
        fact_key = f"material_kind:{filename}"
        kind = effective.get(fact_key)
        if kind is None and fact_key in blocked_kind_keys:
            continue
        if kind is None:
            classified = steps.classify_material(filename, text, usage_ctx=usage_ctx)
            artifacts.setdefault("material_classification", {})[filename] = classified
            if classified["uncertain"] or fact_key in forced:
                pending_kind = classified["uncertain"] or [_question(
                    fact_key, f"“{filename}”主要是什么资料？",
                    "撤销原确认后要重新确定处理步骤，否则可能把内容填进错误位置",
                    "choice", [
                        {"label": "技术参数", "value": "technical"},
                        {"label": "商务要求", "value": "business"},
                        {"label": "评审办法/分值", "value": "scoring"},
                        {"label": "项目基本信息", "value": "basic"},
                        {"label": "其他资料", "value": "other"},
                    ])]
                level = _confidence_label(classified.get("confidence"))
                for item in pending_kind:
                    item["confidence"] = level
                    item["suggestion"] = classified["kind"] if level != "low" else ""
                    item["suggestion_reason"] = (
                        f"模型依据文件名和资料前 1500 字判断为“{_kind_label(classified['kind'])}”："
                        f"{classified.get('reason') or '没有给出可核对理由'}。"
                        "资料类型会决定后续处理步骤，请以原文件内容复核。")
                    if level != "low":
                        for option in item.get("options") or []:
                            option["suggested"] = option.get("value") == classified["kind"]
                questions.extend(pending_kind)
                continue
            kind = classified["kind"]
            update = {"key": fact_key, "value": kind, "source": "model",
                      "evidence": f"模型判断：{classified['reason']}"}
            fact_updates.append(update)
            effective[fact_key] = kind
        processed.append(f"{filename}（{kind}）")

        if kind == "technical":
            rows = steps.parse_clauses(text)
            artifacts.setdefault("technical", {})[filename] = {"A_clauses": rows}
            if not rows:
                notes.append(f"{filename}：没有读到可拆分的编号技术条款")
                continue
            whole_value = effective.get("whole_tops")
            whole = None
            if whole_value is None:
                whole = steps.classify_whole_tops(rows, usage_ctx=usage_ctx)
                artifacts["technical"][filename]["B_whole_tops"] = whole
                whole_questions = whole.get("uncertain") or []
                level = _confidence_label(whole.get("confidence"))
                selected = whole.get("whole_tops") or []
                if whole_questions:
                    leaf_count = steps.calculate(rows, ())
                    whole_count = steps.calculate(rows, selected)
                    quotes = _whole_top_quotes(rows, selected)
                    reason = ""
                    if quotes:
                        reason = "原文可核对：" + "、".join(f"“{x}”" for x in quotes) + "。"
                    model_reasons = [str((whole.get("reason") or {}).get(x) or "")
                                     for x in selected]
                    if any(model_reasons):
                        reason += "我的理解是" + "；".join(x for x in model_reasons if x) + "。"
                    reason += (f"按配置清单整条计数，一般条款是 {whole_count['general']} 条；"
                               f"按子项逐条计数，一般条款会变成 {leaf_count['general']} 条。")
                    # 只说真正有差异的数字；相同数字也拿来对比，
                    # 会让经办人误以为两种口径下的 ▲ 条款有变化。
                    if whole_count["tri"] != leaf_count["tri"]:
                        reason += (f"按配置清单整条计数，▲条款是 {whole_count['tri']} 条；"
                                   f"按子项逐条计数会变成 {leaf_count['tri']} 条。")
                    for item in whole_questions:
                        item["confidence"] = level
                        item["suggestion"] = "whole" if selected and level != "low" else ""
                        item["suggestion_reason"] = reason
                        if selected and item.get("options"):
                            item["options"][0]["suggested"] = level != "low"
                questions.extend(whole_questions)
                # 尚未确认时不把模型候选当成定论；计数暂按逐条口径展示并明确标黄。
                whole_value = []

            score_doc = steps.score_settings(text)
            if score_doc:
                for key in ("total_score", "tri_ratio"):
                    if key not in effective:
                        update = {"key": key, "value": score_doc[key], "source": "document",
                                  "evidence": score_doc["evidence"]}
                        fact_updates.append(update)
                        effective[key] = score_doc[key]

            no_child_rule = re.search(
                r"无子项的条款[^\n]{0,40}以每项条款为\s*1\s*项计算", text)
            child_rule = re.search(
                r"有子项的条款[^\n]{0,40}以最末级的子项为\s*1\s*项计算", text)
            if no_child_rule and child_rule and "count_rule" not in effective:
                evidence = no_child_rule.group(0) + "；" + child_rule.group(0)
                update = {"key": "count_rule", "value": "leaf", "source": "document",
                          "evidence": evidence}
                fact_updates.append(update)
                effective["count_rule"] = "leaf"

            count_rule = effective.get("count_rule")
            counted = steps.calculate(
                rows, whole_value or (), total_score=effective.get("total_score"),
                tri_ratio=effective.get("tri_ratio"),
                count_rule_confirmed=count_rule == "leaf",
            )
            count_questions = counted.get("uncertain") or []
            for item in count_questions:
                item["suggestion"] = "leaf"
                item["suggestion_reason"] = (
                    "这份资料原文没有检出完整计数规则；采购需求模板的通用口径是“无子项每条算 1 项、"
                    "有子项按最末级子项算 1 项”。按此口径可以继续计算；若本项目文件另有原话，"
                    "应改按原文复算。")
                item["confidence"] = "medium"
                if item.get("options"):
                    item["options"][0]["suggested"] = True
            questions.extend(count_questions)
            if count_rule == "other" and "count_rule_detail" not in effective:
                questions.append(_question(
                    "count_rule_detail", "文件规定的其他条款计数规则是什么？请照原文填写。",
                    "现有代码只能按已确认规则复算；没有具体原文就不能把暂算结果当成正式计数",
                    "text", suggestion_reason="现有资料没有可供照抄的其他规则原话，因此不代拟规则。"))
            table = steps.technical_table(rows)
            artifacts["technical"][filename].update({
                "C_count_scores": counted, "D_technical_table": table,
            })
            packages.append({"技术要求": {
                "value": json.dumps(table["blocks"], ensure_ascii=False),
                "evidence": ((rows[0].get("raw") or rows[0].get("text") or "")
                             + "；……；"
                             + (rows[-1].get("raw") or rows[-1].get("text") or ""))[:120],
                "pending": effective.get("whole_tops") is None or count_rule != "leaf",
            }})
            score_text = ("分值待确认" if counted["general_score"] is None else
                          f"一般{counted['general_score']}分、▲{counted['tri_score']}分")
            if count_rule != "leaf":
                prefix = "按模板计数规则暂算"
            elif effective.get("whole_tops") is None:
                prefix = "按逐条口径暂算"
            else:
                prefix = "计数"
            notes.append(f"{prefix}：一般{counted['general']}条、▲{counted['tri']}条；{score_text}")

        elif kind == "business":
            business = steps.business_requirements(text, usage_ctx=usage_ctx)
            artifacts.setdefault("E_business", {})[filename] = business
            if business.get("blocks"):
                source_lines = [line for values in business["sections"].values()
                                for line in values]
                packages.append({"商务要求": {
                    "value": json.dumps(business["blocks"], ensure_ascii=False),
                    "evidence": "；".join(source_lines)[:120],
                }})
        elif kind == "basic":
            basic = steps.basic_information(text, usage_ctx=usage_ctx)
            artifacts.setdefault("F_basic_information", {})[filename] = basic
            if basic.get("项目概况"):
                fields["项目概况"] = {"value": basic["项目概况"],
                                      "evidence": basic["项目概况"][:120]}
            if basic.get("packages") and "package_plan" not in effective:
                plan = [{"包名": x["包名"], "预算金额": x["预算金额"]}
                        for x in basic["packages"]]
                evidence = "；".join(x["evidence"] for x in basic["packages"])[:500]
                update = {"key": "package_plan", "value": plan,
                          "source": "document", "evidence": evidence}
                fact_updates.append(update)
                effective["package_plan"] = plan
        elif kind == "scoring":
            score_doc = steps.score_settings(text)
            if score_doc:
                for key in ("total_score", "tri_ratio"):
                    if key not in effective:
                        update = {"key": key, "value": score_doc[key], "source": "document",
                                  "evidence": score_doc["evidence"]}
                        fact_updates.append(update)
                        effective[key] = score_doc[key]
                notes.append("已从评审办法原文读取技术分总分和▲条款分值比例")
            else:
                notes.append(f"{filename}：没有同时读到一般条款与▲条款的明确分值")
        elif kind == "mixed":
            questions.append(_question(
                fact_key, f"“{filename}”包含多类内容，这一轮先处理哪一部分？",
                "先定处理范围才能避免把商务条款拆进技术参数，或把分值说明填错位置",
                "choice", [
                    {"label": "技术参数", "value": "technical"},
                    {"label": "商务要求", "value": "business"},
                    {"label": "评审办法/分值", "value": "scoring"},
                    {"label": "项目基本信息", "value": "basic"},
                ]))
        else:
            notes.append(f"{filename}：已识别为其他资料，暂不自动填表")

    # 分值设置可能排在技术参数附件后面。等所有已确认类型的资料都处理完，再把
    # 先前的暂算结果复算一次，避免同一轮已经读到 10.5/39.5 却仍显示“待确认”。
    if effective.get("total_score") is not None and effective.get("tri_ratio") is not None:
        for artifact in (artifacts.get("technical") or {}).values():
            rows = artifact.get("A_clauses") or []
            if not rows:
                continue
            counted = steps.calculate(
                rows, effective.get("whole_tops") or (),
                total_score=effective["total_score"], tri_ratio=effective["tri_ratio"],
                count_rule_confirmed=effective.get("count_rule") == "leaf")
            artifact["C_count_scores"] = counted
            for i, note in enumerate(notes):
                if "分值待确认" not in note:
                    continue
                notes[i] = (note.replace(
                    "分值待确认",
                    f"一般{counted['general_score']}分、▲{counted['tri_score']}分"))
                break

    # 这些口径没有事实或原文明文就必须问。按影响面排序后每轮只取前三个；
    # 已经生成的四列表和商务归类仍照常返回，不因待确认而整轮空转。
    required = []
    needs_scores = any(effective.get(f"material_kind:{name}") in ("technical", "scoring")
                       for name, _ in parts)
    if parts and needs_scores:
        if "total_score" not in effective:
            required.append(_question(
                "total_score", "本项目技术分总分是多少？",
                "总分决定一般条款和▲条款各自分到多少分，不能沿用别的项目", "number",
                suggestion=50,
                suggestion_reason="这份资料原文没写技术分总分；同类项目常见按 50 分设置，"
                                  "这是经验值，不是从本文件读出的结论。按 50 分可继续分值计算；"
                                  "若项目采用其他总分，两类条款分值会随之变化。",
                confidence="medium"))
        if "tri_ratio" not in effective:
            required.append(_question(
                "tri_ratio", "▲条款与一般条款的分值怎么分配？请填写两类分值或▲占比。",
                "原文没有明确比例时套默认权重会造成评分办法错误", "text",
                suggestion=0.8,
                suggestion_reason="这份资料原文没写▲条款占比；同类项目常见让▲条款占技术分的 80%，"
                                  "这是经验值，不是原文结论。采用其他占比会直接改变一般条款和▲条款分值。",
                confidence="medium"))
    if parts and "package_plan" not in effective:
        required.append(_question(
            "package_plan", "这个项目分几个包，每个包对应资料的哪一段？",
            "分包边界决定技术、商务要求和预算分别写入哪个采购包", "text",
            suggestion_reason="现有资料没有同时读出明确包数、各包范围和金额，缺一项都可能串包，"
                              "因此不提供建议。", confidence="low"))
    if parts and "price_deduct" not in effective:
        required.append(_question(
            "price_deduct", "价格扣除政策采用哪一项？",
            "小微企业、监狱企业、残疾人福利单位的适用口径要写入采购政策，不能代选",
            "choice", [
                {"label": "小微企业", "value": "small_micro"},
                {"label": "监狱企业", "value": "prison"},
                {"label": "残疾人福利单位", "value": "disabled_welfare"},
            ], suggestion_reason="这是采购政策选择，不是从资料内容能判断的事实，硬给建议会误导，"
                                  "因此由经办人确认。", confidence="low"))
    questions.extend(required)

    deduped = []
    for item in questions:
        if not item.get("why") or item.get("key") in {x["key"] for x in deduped}:
            continue
        if item.get("key") in effective:
            continue
        item.setdefault("kind", "text")
        item.setdefault("options", [])
        item.setdefault("suggestion", "")
        item.setdefault("suggestion_reason", "")
        item.setdefault("confidence", "low")
        deduped.append(item)
    questions = deduped[:3]

    for name in set(locked_names):
        fields.pop(name, None)

    if parts:
        say = "已处理：" + "、".join(processed) if processed else "这轮资料需要先确认类型。"
        instruction = intent.get("instruction") or (user_text or "").strip()
        if instruction:
            say += "\n本轮说明：" + instruction[:100]
        if fact_updates:
            confirmed = [x["key"] for x in fact_updates if x["source"] == "user"]
            if confirmed:
                say += "\n已确认：" + "、".join(confirmed)
        if questions:
            say += f"\n还有 {len(questions)} 项会影响结果，请确认；不受影响的内容已先整理出来。"
        return {"say": say, "fields": fields, "packages": packages,
                "notes": notes, "questions": questions, "facts": fact_updates,
                "steps": artifacts, "intent": intent["intent"]}

    usable = [(n, k, h) for n, k, h in AGENT_FIELDS if n not in set(locked_names)]
    spec = "、".join(n for n, _k, _h in usable)
    pkg_spec = "、".join(n for n, _h in AGENT_PACKAGE_FIELDS)

    lines = [f"可填的字段：{spec}",
             f"每个采购包还可填：{pkg_spec}", ""]
    # 只带最近若干轮，别把上下文撑爆。
    # **之前传过的资料要一起带**——不带的话第二轮就失忆了：
    # 人问「质保期多久」，它会说「我还没看到资料」（实测踩到）。
    # 老资料截短一些，最新那份给足。
    past = []
    for h in history[-12:]:
        who = "经办人" if h.get("role") == "user" else "你"
        txt = (h.get("text") or "").strip()
        if txt:
            lines.append(f"{who}：{txt}")
        mat = (h.get("material") or "").strip()
        if mat:
            past.append(mat)
    if past:
        lines.append("")
        lines.append("经办人之前传过的资料（供你回答追问时参考）：")
        lines.append("--------")
        lines.append(("\n\n".join(past))[-12000:])
        lines.append("--------")
    if material.strip():
        lines.append("")
        lines.append("经办人这次传来的资料原文：")
        lines.append("--------")
        lines.append(material[:22000])
        lines.append("--------")
    lines.append("")
    lines.append(f"经办人：{user_text.strip() or '（只传了资料，没说话）'}")

    # 普通问答同样把本轮原话放在 prompt 最后，使它高于历史和模型自己的判断。
    if facts:
        lines.insert(0, "本次已确认事实：" + json.dumps(_fact_values(facts), ensure_ascii=False))
    user = _bounded_user(CHAT_SYSTEM, "\n".join(lines))
    out = llm_client.chat(CHAT_SYSTEM, user,
                          temperature=0.2, max_tokens=2000, usage_ctx=usage_ctx)
    say, data = _split_reply(out)

    fields, pkgs, notes = {}, [], []
    if isinstance(data, dict):
        allow = {n for n, _k, _h in usable}
        for k, v in (data.get("fields") or {}).items():
            if k not in allow:
                notes.append(f"{k}：不在可填范围，没采纳")
                continue
            val = v.get("value") if isinstance(v, dict) else v
            ev = v.get("evidence") if isinstance(v, dict) else ""
            if val is None or str(val).strip() == "":
                continue
            if not str(ev or "").strip():
                notes.append(f"{k}：没给原文依据，没采纳")
                continue
            fields[k] = {"value": str(val).strip(), "evidence": str(ev).strip()[:120]}

        pkg_allow = {n for n, _h in AGENT_PACKAGE_FIELDS}
        for one in (data.get("packages") or [])[:20]:
            if not isinstance(one, dict):
                continue
            row = {}
            for k, v in one.items():
                if k not in pkg_allow:
                    continue
                val = v.get("value") if isinstance(v, dict) else v
                ev = v.get("evidence") if isinstance(v, dict) else ""
                if val is None or str(val).strip() == "":
                    continue
                if not str(ev or "").strip():
                    notes.append(f"包·{k}：没给原文依据，没采纳")
                    continue
                row[k] = {"value": str(val).strip(), "evidence": str(ev).strip()[:120]}
            if row:
                pkgs.append(row)

    if not say:
        say = "（这一轮没什么要说的）" if not fields and not pkgs else "读完了，下面这些可以填："
    return {"say": say, "fields": fields, "packages": pkgs, "notes": notes,
            "questions": [], "facts": fact_updates, "intent": intent["intent"]}
