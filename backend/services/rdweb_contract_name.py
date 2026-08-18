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
    name = re.sub(r"[\s　]+", "", name).strip("-_ ")
    # 别把成对括号的右半边当垃圾字符剥掉：「医用耗材购销协议(电切环)」被剥成
    # 「医用耗材购销协议(电切环」是 2026-08-15 实测踩到的。只有左右不配对时才去。
    while name and name[-1] in "（(" :
        name = name[:-1].strip("-_ ")
    if name.count("(") + name.count("（") < name.count(")") + name.count("）"):
        name = name.rstrip(")）").strip("-_ ")
    return name


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

# ══════════════════════════════════════════════════════════════════
# 2026-08-18 重做：合同名称 = 合同类型名 + 项目名称 + 包号
#
# 原来只有「猜出来的类型名 + 项目名」，两个毛病：
#   ① 没有包号，一个项目多个包时审签单上分不出是哪个包的合同；
#   ② 类型名靠猜附件文件名，实测把整个文件名（含编号和供应商名）当成了类型名——
#      「内江市第一人民医院服务合同_NJYYJX-SY-2607010（第二次）-蓉旭阳」。
# 现在类型名以**经办人审核时确认的** contracts.contract_type 为准，下面的猜测
# 只用来给他填默认值，猜错了他改一下就是，不再直接决定推出去的内容。
# ══════════════════════════════════════════════════════════════════

# 医院实际在用的几种，按出现频率排；界面上做成下拉+可自己填。
COMMON_CONTRACT_TYPES = [
    "医用耗材购销协议",
    "医疗器械购销协议",
    "医疗设备购销合同",
    "服务合同",
    "配送服务合同",
    "维保服务合同",
    "工程施工合同",
    "货物采购合同",
    "试剂购销协议",
    "租赁合同",
]

# 猜类型名时只认这些词根：命中就取「词根本身」，绝不把整个文件名端过来。
_TYPE_WORDS = [
    "医用耗材购销协议", "医疗器械购销协议", "医疗设备购销合同", "试剂购销协议",
    "配送服务合同", "维保服务合同", "工程施工合同", "货物采购合同",
    "购销协议", "购销合同", "采购合同", "服务合同", "租赁合同", "施工合同",
]


def guess_contract_type(*texts) -> str:
    """从附件文件名等文本里认出合同类型词根。认不出返回空，让人去填。"""
    blob = "　".join(str(t or "") for t in texts)
    blob = re.sub(r"[\s　]+", "", blob)
    for word in _TYPE_WORDS:          # 长的排前面，先匹配更具体的
        if word in blob:
            return word
    return ""


def compose_name(contract_type: str, project_name: str, package_no) -> str:
    """合同类型名 + 项目名称 + 包号 —— 用户 2026-08-18 明确的口径。"""
    ctype = re.sub(r"[\s　]+", "", str(contract_type or "").strip())
    proj = str(project_name or "").strip()
    pkg = str(package_no or "").strip() or "1"
    head = f"{ctype}{SEP}{proj}" if ctype and ctype not in proj else (ctype or proj)
    return f"{head}　包{pkg}" if head else f"包{pkg}"
