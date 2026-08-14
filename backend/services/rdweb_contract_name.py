"""rd-web 合同审签单的「合同名称」：真实合同名称 + 项目名称。

手绘计划⑤的意见：现在推过去的合同名称只是**项目名称**（如「2026年宫腔镜电切环
西1区服务采购项目」），审签单上看不出这份到底是什么合同。正确口径是
**合同附件里的真实合同名称 + 项目名称**。

取真实合同名称的顺序（都拿不到就退回原值，绝不把推送卡住）：
  1. 合同主附件的文件名（去扩展名、去开头的编号/日期），须含「合同/协议」；
  2. 附件正文前若干行里找一行像标题的（含「合同/协议」且不太长）。
"""
import os
import re

SEP = "-"
_KEY = ("合同", "协议")
# 文件名开头常见的编号/日期前缀：2026-08-14、20260814、NJYY-2026-001、01. 等。
# 注意别把「2026年宫腔镜…」这种正文里的年份当前缀吃掉——所以纯数字必须后面跟
# 分隔符，「年」不算分隔符。
_PREFIX = re.compile(
    r"^[\s（(]*"
    r"(?:\d{4}[-.]\d{1,2}[-.]\d{1,2}"          # 2026-08-14 / 2026.8.14
    r"|\d{6,8}"                                  # 20260814
    r"|[A-Za-z]{2,}[-_]?\d+(?:[-_]\d+)*"        # NJYY-2026-001
    r"|\d{1,3}[.、)）]"                          # 01. / 1、
    r")[\s\-_.、)）]*")


def _clean(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"\.(docx?|pdf|wps|jpe?g|png|zip)$", "", name, flags=re.I)
    name = _PREFIX.sub("", name)
    return re.sub(r"[\s　]+", "", name).strip("-_（）() ")


def _looks_like_title(text: str) -> bool:
    t = (text or "").strip()
    return bool(t) and 4 <= len(t) <= 40 and any(k in t for k in _KEY)


def title_from_attachments(attachments) -> str:
    """从附件（[{"path","name"}...]，第一个通常是合同主文件）里找真实合同名称。"""
    for att in attachments or []:
        cand = _clean(att.get("name") or os.path.basename(att.get("path") or ""))
        if _looks_like_title(cand):
            return cand
    # 文件名不成样子时再读正文首屏（读取失败就算了，不影响推送）
    for att in (attachments or [])[:1]:
        try:
            from services.rdweb_autofill import extract_file_text
            text = extract_file_text(att.get("path") or "") or ""
        except Exception:
            continue
        for line in [ln.strip() for ln in text.splitlines() if ln.strip()][:15]:
            line = re.sub(r"[\s　]+", "", line)
            if _looks_like_title(line):
                return line
    return ""


def compose(contract_name: str, project_name: str, attachments) -> str:
    """拼出送去 rd-web 的合同名称。"""
    cur = (contract_name or "").strip()
    proj = (project_name or "").strip()
    real = title_from_attachments(attachments)
    if not real:
        # 附件里读不出来时，合同表里的名字若本身不是项目名，就当作真实合同名
        real = cur if cur and cur != proj else ""
    if not real:
        return cur or proj
    if not proj or proj in real:
        return real
    return f"{real}{SEP}{proj}"
