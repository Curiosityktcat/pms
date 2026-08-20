# -*- coding: utf-8 -*-
"""采购需求 Agent 的分步编排。

模型只做语义分类并返回短引用；原文、条款、计数、分值和金额都由代码处理。
每个公开函数都是一个可单独查看、单独重跑的步骤。
"""
import re
import time

from services import clause_parser


PROMPT_CHAR_LIMIT = 4000
_FALSE_GROUP_RE = re.compile(
    r"[。；;，,]$|[≥≤<>＝=]|^【.*】$|(?:金额|限价).*元$|"
    r"^(?:技术|参数|技术参数)[。.:：]?$|^包[一二三四五六七八九十\d]+[：:]?$"
)
_PACKAGE_RE = re.compile(r"(?:采购)?包\s*([一二三四五六七八九十\d]+)\s*[：:]")
_AMOUNT_RE = re.compile(r"(?:预算金额|合计金额)\s*([0-9０-９][0-9０-９,，.．]*\s*(?:万元|万|元))")

WHOLE_SYSTEM = """你只判断采购技术条款中哪些顶层条款是配置清单、货物明细或附件列表。
这类顶层条款的子项是货物组成，不应拆成多个评分条款。只输出JSON：
{"whole_tops":["候选ID"],"reason":{"候选ID":"短理由"},"confidence":0.0}。
confidence 表示仅凭这份短目录作此判断的把握，只能选择给出的候选ID。"""

MATERIAL_SYSTEM = """你只判断一份采购资料的类型，不提取、不改写其中事实。资料类型只能是：
technical（技术参数）、business（商务要求）、scoring（评审办法或分值设置）、
basic（项目基本信息）、mixed（包含好几类）、other（其他）。只输出JSON：
{"kind":"technical","confidence":0.0,"reason":"一句短理由"}。"""

BASIC_SYSTEM = """你只做采购包边界确认，不生成或改写事实。根据带L编号的原文行，输出JSON：
{"package_lines":{"包一":["L1"],"包二":["L2"],"包三":["L3"]},"overview_line":"L0"}。
金额、名称和正文不要输出，只返回原文行号；没有则留空。"""

BUSINESS_SYSTEM = """你只把原文行号归类为商务要求。只输出JSON：
{"交货期及地点":["L1"],"质量保证":["L2"],"售后服务":["L3"],"其他":[]}。
只能引用给出的行号，不得复述、生成或改写原文。"""


def _jsonable_rows(rows):
    """复制为适合 JSON 的行，避免调用方意外改动解析结果。"""
    out = []
    for row in rows:
        item = dict(row)
        item["parts"] = list(item.get("parts") or [])
        out.append(item)
    return out


def _is_group_title(line):
    line = (line or "").strip().rstrip("：:")
    if not line or len(line) > clause_parser.GROUP_MAX:
        return False
    if clause_parser.NUM_RE.match(line) or _FALSE_GROUP_RE.search(line):
        return False
    return True


def parse_clauses(text):
    """步骤 A：调用既有解析器，并仅在编排层修正设备分组。

    Word 自动编号偶尔不会出现在 ``paragraph.text`` 中，所以设备名和紧随其后的
    参数行可能被解析器混淆；另有一行“技术。”会被当成设备名。这里依据原文中的
    短标题重新给已解析行贴 group，不修改 clause_parser.parse/count。
    """
    original_text = text or ""
    # read_files 会用【文件名】拼接多份附件。分值设置/相关说明若紧跟参数文件，
    # 其中的长段落会被基础解析器续到最后一个条款；先按附件切开，只组合确实含
    # 多个编号条款的区段，避免“评分说明粘到 15.12”这类污染。
    sections = re.split(r"(?m)^【[^\n】]+】\s*$", original_text)
    technical_sections = []
    for section in sections:
        if len(clause_parser.parse(section)) >= 3:
            technical_sections.append(section)
    text = "\n".join(technical_sections) if technical_sections else original_text
    rows = clause_parser.parse(text)
    if not rows:
        return []

    # 按原文重放一次分组状态，并与 parse 产出的编号行逐一对应。
    ri = 0
    group = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if clause_parser.NUM_RE.match(line):
            if ri < len(rows):
                rows[ri]["group"] = group
                ri += 1
        elif _is_group_title(line):
            group = line.rstrip("：:")

    # 同一设备的顶层编号重新从 1 开始时，形成独立参数组。2025 案例第二段
    # 高频手术能量平台正是这种格式；名称取自重置前的原文条款，不凭空生成。
    seen_one = set()
    override = None
    base_group = None
    previous = None
    for row in rows:
        current_group = row.get("group") or ""
        if current_group != base_group:
            base_group, override = current_group, None
        if row.get("level") == 1 and row.get("no") == "1":
            if current_group in seen_one:
                source = (previous or {}).get("text", "")
                m = re.search(r"(?:具备|配置)?([^，；。]{2,24}(?:平台|系统|设备|仪))", source)
                if m:
                    override = m.group(1).strip()
            seen_one.add(current_group)
        if override:
            row["group"] = override
        previous = row

    # “技术。”后的 19~21 是上一段的续条，不能另建分组。重放逻辑通常已处理，
    # 这里再兜住其它类似的短句误标题。
    last_valid = ""
    for row in rows:
        g = row.get("group") or ""
        if g and _FALSE_GROUP_RE.search(g):
            row["group"] = last_valid
        elif g:
            last_valid = g
    return _jsonable_rows(rows)


def _restore_rows(rows):
    out = []
    for row in rows or []:
        item = dict(row)
        item["parts"] = tuple(item.get("parts") or tuple(int(x) for x in str(item["no"]).split(".")))
        out.append(item)
    return out


def _top_candidates(rows):
    """只给模型有子项的顶层目录；叶子顶层不可能“整条不拆”。"""
    items = _restore_rows(rows)
    candidates = []
    for row in items:
        if row.get("level") != 1 or row.get("is_leaf"):
            continue
        group = row.get("group") or ""
        ident = f"{group}|{row['no']}" if group else str(row["no"])
        candidates.append({
            "id": ident,
            "group": group,
            "no": str(row["no"]),
            "mark": row.get("mark") or "",
            "preview": (row.get("text") or "")[:30],
        })
    return candidates


def _bounded(system, user):
    """硬限制一次模型调用的 system+user 总字符数。"""
    room = max(0, PROMPT_CHAR_LIMIT - len(system))
    return user[:room], len(system) + min(len(user), room)


def _call_json(system, user, *, usage_ctx=None, max_tokens=2000):
    from services import llm_client
    user, prompt_chars = _bounded(system, user)
    # 模型偶尔会把思考耗到输出不完整；这里留一次重试和足够等待时间，
    # 否则一次瞬时抖动就会让整轮资料处理失败。
    raw = llm_client.chat(system, user, temperature=0.0, max_tokens=max_tokens,
                          timeout=120, retries=1, usage_ctx=usage_ctx,
                          response_format={"type": "json_object"})
    from services.demand_agent import _clean_json
    data = _clean_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("模型没有返回可解析的短结论")
    return data, prompt_chars


def classify_whole_tops(rows, *, usage_ctx=None):
    """步骤 B：模型从短目录中选出应整条计数的顶层条款。"""
    started = time.monotonic()
    candidates = _top_candidates(rows)
    if not candidates:
        return {"whole_tops": [], "reason": {}, "confidence": 1.0,
                "uncertain": [], "prompt_chars": 0,
                "elapsed_seconds": round(time.monotonic() - started, 3)}
    directory = "\n".join(
        f"{x['id']}\t{x['mark']}\t{x['preview']}" for x in candidates
    )
    user = "候选目录（候选ID、标记、正文前30字）：\n" + directory
    data, prompt_chars = _call_json(WHOLE_SYSTEM, user, usage_ctx=usage_ctx)
    allowed = {x["id"]: x for x in candidates}
    selected = []
    for value in data.get("whole_tops") or []:
        ident = str(value).strip()
        if ident in allowed and ident not in selected:
            selected.append(ident)
    reason_in = data.get("reason") if isinstance(data.get("reason"), dict) else {}
    reason = {x: str(reason_in.get(x) or "")[:80] for x in selected}
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    uncertain = []
    # 这一步一旦选中清单项，子项会从逐条计数改为整条计数，影响面太大。
    # 短目录只能给出候选，最终口径交给经办人确认，避免“模型很自信地算错”。
    if selected:
        labels = "、".join(selected)
        uncertain.append({
            "key": "whole_tops",
            "ask": f"模型认为第 {labels} 条可能是配置清单。它们应整条算 1 项，还是子项逐条计数？",
            "why": "这会直接改变技术条款数量和每类条款的评审分值",
            "kind": "choice",
            "options": [
                {"label": "是配置清单，整条算 1 项", "value": selected},
                {"label": "是技术参数，逐条计数", "value": []},
            ],
        })
    elif confidence < 0.75 and candidates:
        uncertain.append({
            "key": "whole_tops",
            "ask": "这些带子项的顶层条款中，有没有配置清单、货物明细或附件列表？",
            "why": "清单应整条计数，技术参数则按最末级子项计数，选错会改变条款总数",
            "kind": "text", "options": [],
        })
    return {"whole_tops": selected, "reason": reason, "confidence": confidence,
            "uncertain": uncertain,
            "prompt_chars": prompt_chars,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def classify_material(filename, text, *, usage_ctx=None):
    """资料类型判断：只给文件名和前 1500 字，拿不准就上报而不继续猜。"""
    started = time.monotonic()
    excerpt = (text or "")[:1500]
    user = f"文件名：{filename or '未命名资料'}\n资料前1500字：\n{excerpt}"
    data, prompt_chars = _call_json(MATERIAL_SYSTEM, user, usage_ctx=usage_ctx)
    allowed = {"technical", "business", "scoring", "basic", "mixed", "other"}
    kind = str(data.get("kind") or "other").strip().lower()
    if kind not in allowed:
        kind = "other"
    try:
        confidence = max(0.0, min(1.0, float(data.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    reason = str(data.get("reason") or "")[:120]
    uncertain = []
    if confidence < 0.75 or kind == "mixed":
        key = f"material_kind:{filename or '未命名资料'}"
        uncertain.append({
            "key": key,
            "ask": f"“{filename or '这份资料'}”主要是什么资料？",
            "why": "资料类型决定走技术拆条、商务归类还是分值读取；判错会把内容填进错误位置",
            "kind": "choice",
            "options": [
                {"label": "技术参数", "value": "technical"},
                {"label": "商务要求", "value": "business"},
                {"label": "评审办法/分值", "value": "scoring"},
                {"label": "项目基本信息", "value": "basic"},
                {"label": "混合资料", "value": "mixed"},
                {"label": "其他资料", "value": "other"},
            ],
        })
    return {"kind": kind, "confidence": confidence, "reason": reason,
            "uncertain": uncertain, "prompt_chars": prompt_chars,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def whole_top_keys(values):
    """把接口使用的 group|no 引用转为 clause_parser.count 所需键。"""
    out = []
    for value in values or []:
        if isinstance(value, (list, tuple)) and len(value) == 2:
            out.append((str(value[0]), str(value[1])))
            continue
        value = str(value)
        if "|" in value:
            group, no = value.rsplit("|", 1)
            out.append((group, no))
        else:
            out.append(value)
    return out


def calculate(rows, whole_tops=(), *, total_score=None, tri_ratio=None,
              count_rule_confirmed=True):
    """步骤 C：代码计数并分值；模型不参与数字。"""
    result = clause_parser.count(_restore_rows(rows), whole_top_keys(whole_tops))
    if total_score is None or tri_ratio is None:
        scores = {"general_score": None, "tri_score": None}
    else:
        scores = clause_parser.split_scores(result["general"], result["tri"],
                                             total_score=float(total_score), tri_ratio=tri_ratio)
    # items 很大且包含 tuple，接口仅返回可复核引用；原始 rows 由步骤 A 保存。
    refs = [{"group": x.get("group") or "", "no": x["no"],
             "mark": x.get("mark") or "", "count_as": x["count_as"]}
            for x in result["items"]]
    uncertain = []
    if not count_rule_confirmed:
        uncertain.append({
            "key": "count_rule",
            "ask": "请确认计数规则是否为：‘（1）无子项的条款：以每项条款为1项计算；（2）有子项的条款：以最末级的子项为1项计算’？",
            "why": "计数口径会改变一般条款和▲条款数量，进而影响分值分配",
            "kind": "choice",
            "options": [
                {"label": "按这个规则", "value": "leaf"},
                {"label": "文件另有规则", "value": "other"},
            ],
        })
    return {"general": result["general"], "star": result["star"],
            "tri": result["tri"], "total": result["total"],
            **scores, "items": refs, "uncertain": uncertain}


def score_settings(text):
    """从分值设置原文逐字读取一般/▲分值，未同时出现就返回 None。"""
    general = re.search(
        r"一般条款得分[^\n]{0,120}?[×xX]\s*([0-9]+(?:\.[0-9]+)?)\s*分", text or "")
    tri = re.search(
        r"[“\"']?▲[”\"']?条款得分[^\n]{0,120}?[×xX]?\s*"
        r"([0-9]+(?:\.[0-9]+)?)\s*分", text or "")
    if not general or not tri:
        return None
    general_score, tri_score = float(general.group(1)), float(tri.group(1))
    total = general_score + tri_score
    if total <= 0:
        return None
    evidence_start = max(0, min(general.start(), tri.start()) - 20)
    evidence_end = min(len(text or ""), max(general.end(), tri.end()) + 20)
    return {"total_score": total, "tri_ratio": tri_score / total,
            "general_score": general_score, "tri_score": tri_score,
            "evidence": (text or "")[evidence_start:evidence_end].strip()[:300]}


def _requirement_name(row, parents):
    group = row.get("group") or ""
    if group:
        return group
    top = str(row["no"]).split(".", 1)[0]
    source = parents.get(top, "")
    if "：" in source:
        return source.split("：", 1)[0].strip() or "技术要求"
    if ":" in source:
        return source.split(":", 1)[0].strip() or "技术要求"
    return source if source and len(source) <= 20 else "技术要求"


def technical_table(rows):
    """步骤 D：代码生成四列表。★▲ 与编号不再粘在正文里。"""
    items = _restore_rows(rows)
    parents = {str(x["no"]).split(".", 1)[0]: x.get("text") or ""
               for x in items if x.get("level") == 1}
    table = []
    for row in items:
        table.append({
            "参数性质": row.get("mark") or "",
            "序号": str(row["no"]),
            "技术要求名称": _requirement_name(row, parents),
            "技术要求内容": row.get("text") or "",
            "分组": row.get("group") or "",
        })
    block = {"kind": "table",
             "header": ["参数性质", "序号", "技术要求名称", "技术要求内容（性能指标）"],
             "rows": [[x["参数性质"], x["序号"], x["技术要求名称"], x["技术要求内容"]]
                      for x in table]}
    return {"columns": block["header"], "rows": table, "blocks": [block],
            "uncertain": []}


def _numbered_source_lines(text, keywords=None):
    out = []
    for i, raw in enumerate((text or "").splitlines()):
        line = raw.strip()
        if not line:
            continue
        if keywords and not any(k in line for k in keywords):
            continue
        out.append((f"L{i}", line))
    return out


def business_requirements(text, *, usage_ctx=None):
    """步骤 E：模型只归类行号，代码按引用取回商务原文。"""
    started = time.monotonic()
    keys = ("交货", "履约", "质保", "保修", "售后", "培训", "验收", "付款", "支付")
    source = _numbered_source_lines(text, keys)
    if not source:
        return {"sections": {}, "blocks": [], "uncertain": [], "prompt_chars": 0,
                "elapsed_seconds": round(time.monotonic() - started, 3)}
    user = "待归类原文：\n" + "\n".join(f"{k}\t{v}" for k, v in source)
    data, prompt_chars = _call_json(BUSINESS_SYSTEM, user, usage_ctx=usage_ctx)
    lookup = dict(source)
    sections = {}
    for category, refs in data.items():
        if not isinstance(refs, list):
            continue
        values = [lookup[str(ref)] for ref in refs if str(ref) in lookup]
        if values:
            sections[str(category)] = values
    blocks = [{"kind": "p", "text": f"{category}：" + "\n".join(values)}
              for category, values in sections.items()]
    return {"sections": sections, "blocks": blocks, "uncertain": [], "prompt_chars": prompt_chars,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def _cn_package(value):
    digits = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
              "6": "六", "7": "七", "8": "八", "9": "九", "10": "十"}
    return "包" + digits.get(value, value)


def basic_information(text, *, usage_ctx=None, confirm_with_model=True):
    """步骤 F：模型确认包边界，代码逐字提取项目概况和各包预算。"""
    started = time.monotonic()
    source = _numbered_source_lines(text, ("项目概况", "预算", "限价", "包", "模板"))
    prompt_chars = 0
    model_refs = {}
    if confirm_with_model and source:
        user = "相关信息原文：\n" + "\n".join(f"{k}\t{v}" for k, v in source)
        data, prompt_chars = _call_json(BASIC_SYSTEM, user, usage_ctx=usage_ctx)
        model_refs = data

    overview = ""
    template = ""
    packages = {}
    for ref, line in source:
        if "项目概况：" in line and not overview:
            overview = line.split("项目概况：", 1)[1].strip()
        if "模板文件是：" in line and not template:
            template = line.split("模板文件是：", 1)[1].strip()
        match = _PACKAGE_RE.search(line)
        if not match:
            continue
        name = _cn_package(match.group(1))
        amounts = _AMOUNT_RE.findall(line)
        if not amounts:
            continue
        # 有“合计金额”时最后一个就是包预算；否则该行唯一预算就是包预算。
        budget = amounts[-1].replace(" ", "")
        packages[name] = {"预算金额": budget, "evidence": line, "source_ref": ref}

    ordered = [{"包名": name, **value} for name, value in packages.items()]
    return {"项目概况": overview, "模板文件": template,
            "包数": len(ordered), "packages": ordered,
            "model_refs": model_refs, "uncertain": [], "prompt_chars": prompt_chars,
            "elapsed_seconds": round(time.monotonic() - started, 3)}


def run(text, *, total_score=None, tri_ratio=None, usage_ctx=None,
        include_basic=True):
    """按 A→B→C→D（以及有相关信息时的 F）运行完整短流程。"""
    started = time.monotonic()
    explicit_scores = score_settings(text) if tri_ratio is None else None
    if explicit_scores:
        total_score = explicit_scores["total_score"]
        tri_ratio = explicit_scores["tri_ratio"]
    rows = parse_clauses(text)
    whole = classify_whole_tops(rows, usage_ctx=usage_ctx)
    provisional_whole = [] if whole.get("uncertain") else whole["whole_tops"]
    counted = calculate(rows, provisional_whole, total_score=total_score,
                        tri_ratio=tri_ratio, count_rule_confirmed=False)
    table = technical_table(rows)
    basic = None
    if include_basic and any(k in text for k in ("项目概况", "预算金额", "合计金额")):
        basic = basic_information(text, usage_ctx=usage_ctx)
    uncertain = ((whole.get("uncertain") or []) + (counted.get("uncertain") or []))
    return {"A_clauses": rows, "B_whole_tops": whole, "C_count_scores": counted,
            "D_technical_table": table, "F_basic_information": basic,
            "uncertain": uncertain,
            "elapsed_seconds": round(time.monotonic() - started, 3)}
