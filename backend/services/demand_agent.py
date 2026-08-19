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

SYSTEM = """你是医院采购部的需求编制助手。你的任务是从用户给的资料里**摘取**信息，
填进《采购需求表》的相应字段。

铁律（违反就是事故）：
1. 只摘原文里有的内容，**绝不推断、绝不补全、绝不换算**。原文没写就留空。
2. **金额、编号、日期、单位名称一律照抄原文**，一个字都不许改写或估算。
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


def suggest(material, instruction="", locked_names=(), usage_ctx=None):
    """让模型给建议。返回 {"fields":{...}, "packages":[...], "notes":[...]}。

    locked_names 是字段字典判定为锁定的字段——Agent 连建议都不给。
    """
    from services import llm_client

    usable = [(n, k, h) for n, k, h in AGENT_FIELDS if n not in set(locked_names)]
    spec = "\n".join(f"- {n}（{h}）" if h else f"- {n}" for n, _k, h in usable)
    pkg_spec = "\n".join(f"- {n}（{h}）" for n, h in AGENT_PACKAGE_FIELDS)

    user = f"""可填的字段：
{spec}

每个采购包还可以填（packages 数组，一个包一项）：
{pkg_spec}

{('额外要求：' + instruction) if instruction.strip() else ''}

以下是资料原文：
--------
{material[:24000]}
--------"""

    out = llm_client.chat(SYSTEM, user, temperature=0.1, max_tokens=3000,
                          usage_ctx=usage_ctx)
    data = _clean_json(out)
    if not isinstance(data, dict):
        raise RuntimeError("模型没有返回可解析的结果，请重试或换一份资料")

    # 过一遍：只保留白名单里的字段，且必须带 evidence
    allow = {n for n, _k, _h in usable}
    fields = {}
    dropped = []
    for k, v in (data.get("fields") or {}).items():
        if k not in allow:
            dropped.append(f"{k}（不在可填范围）")
            continue
        if isinstance(v, dict):
            val, ev = v.get("value"), v.get("evidence")
        else:
            val, ev = v, ""
        if val is None or str(val).strip() == "":
            continue
        if not str(ev or "").strip():
            dropped.append(f"{k}（没给原文依据）")
            continue
        fields[k] = {"value": str(val).strip(), "evidence": str(ev).strip()[:120]}

    pkgs = []
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
                dropped.append(f"包·{k}（没给原文依据）")
                continue
            row[k] = {"value": str(val).strip(), "evidence": str(ev).strip()[:120]}
        if row:
            pkgs.append(row)

    notes = [str(x) for x in (data.get("notes") or [])][:8]
    if dropped:
        notes.append("这些没采纳：" + "、".join(dropped[:6]))
    return {"fields": fields, "packages": pkgs, "notes": notes}


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
1. 只摘原文里有的，**绝不推断、绝不补全、绝不换算**。
2. **金额、编号、日期、单位名称一律照抄原文**，一个字都不许改写或估算。
3. 每条建议都要带 evidence（原文依据，照抄，不超过 80 字）。给不出依据就别填。
4. 这些文件要盖章对外发——留空是安全的，编一个是危险的。

回复格式：先写给人看的话（纯文本，别用 markdown 标题），
如果这一轮有可填的内容，再另起一行输出一个 JSON 块，用 ```json 围起来：
```json
{"fields": {"字段名": {"value": "值", "evidence": "原文依据"}},
 "packages": [{"技术要求": {"value": "...", "evidence": "..."}}]}
```
没有可填内容时**不要输出 JSON 块**，只说话就行。"""


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


def converse(history, user_text, material="", locked_names=(), usage_ctx=None):
    """对话一轮。

    history: [{"role": "user"/"agent", "text": ...}, ...]，按时间正序
    material: 这一轮新传的文件读出来的文字（可空）
    返回 {"say": 给人看的话, "fields": {...}, "packages": [...], "notes": [...]}
    """
    from services import llm_client

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

    out = llm_client.chat(CHAT_SYSTEM, "\n".join(lines),
                          temperature=0.2, max_tokens=3000, usage_ctx=usage_ctx)
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
    return {"say": say, "fields": fields, "packages": pkgs, "notes": notes}
