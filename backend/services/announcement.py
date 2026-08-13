"""
采购公告生成服务
"""
import copy
import io
import os
from docx import Document
from docx.text.paragraph import Paragraph

from models.announcement import QUALIFICATIONS_DEFAULT

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "医院模板", "1.盖章文件", "采购公告.docx",
)

ROUND_CN = ["", "一", "二", "三", "四", "五"]


def _r(para, idx):
    runs = para.runs
    return runs[idx] if idx < len(runs) else None


def _set(para, idx, text):
    r = _r(para, idx)
    if r is not None:
        r.text = text


def _clear_from(para, start_idx):
    for i in range(start_idx, len(para.runs)):
        para.runs[i].text = ""


def _set_para(para, text):
    """把整段替换为单一文本（首 run 写入，其余清空，保留段落格式）。"""
    if not para.runs:
        return
    para.runs[0].text = text
    for r in para.runs[1:]:
        r.text = ""


_CN_DIGITS = "零一二三四五六七八九"


def _cn_num(n):
    """1..99 的中文数字：十、十一、二十、二十一…（条目编号够用）。"""
    if n <= 0:
        return str(n)
    if n < 10:
        return _CN_DIGITS[n]
    if n == 10:
        return "十"
    if n < 20:
        return "十" + _CN_DIGITS[n - 10]
    tens, ones = divmod(n, 10)
    return _CN_DIGITS[tens] + "十" + (_CN_DIGITS[ones] if ones else "")


def _numbered(i, line):
    """给条目加「（一）（二）…（十一）…」编号；若本身已带（X）则原样返回。"""
    if line.startswith("（") or line.startswith("("):
        return line
    return f"（{_cn_num(i + 1)}）{line}"


def generate(project, ann, agency_name):
    """
    生成采购公告 Word 文档，返回 BytesIO。
    attachment_names: 附件文件名列表（写入文档末尾）
    """
    doc = Document(TEMPLATE_PATH)
    ps = doc.paragraphs

    project_name = project.name or ""
    project_number = project.number or ""

    # 第二次及以后的竞选，标题/正文叙述以及 1.2 采购项目名称都追加「（第二次）」等，
    # 以体现这是第几次竞选（第一次不带后缀）。
    round_suffix = ""
    if ann.round_number and ann.round_number > 1:
        cn = ROUND_CN[min(ann.round_number, len(ROUND_CN) - 1)]
        round_suffix = f"（第{cn}次）"
    project_name_round = project_name + round_suffix

    # ── 标题 Para[0] ──────────────────────────────────────────────
    _set(ps[0], 1, "")
    _set(ps[0], 2, project_name_round)
    _set(ps[0], 3, "院内竞选公告")

    # ── 正文 Para[2] ──────────────────────────────────────────────
    _set(ps[2], 0, agency_name)
    _set(ps[2], 4, project_name_round)

    # ── 项目编号 Para[3] ──────────────────────────────────────────
    _set(ps[3], 2, project_number + "；")

    # ── 项目名称 Para[4]：随第几次变化（第二次及以后带「（第二次）」）──
    _set(ps[4], 2, project_name_round + "；")

    # ── 招标项目简介 Para[6] ──────────────────────────────────────
    _set(ps[6], 0, ann.project_intro or "")

    # ── 一般资格要求 一、Para[11-17]：按行填充 qualifications，支持任意条数 ──
    # 模板预留 7 个槽位（（一）~（七)）。条数 >7 时克隆末槽位插入，<7 时删除多余空槽位，
    # 避免编辑新增的条目（超过 7 条）被丢弃。条目文本自带「（X）」编号，直接整行写入。
    qual_text = (ann.qualifications or QUALIFICATIONS_DEFAULT).strip()
    qual_lines = [line.strip() for line in qual_text.split("\n") if line.strip()] or [""]
    QUAL_SLOTS = 7
    qual_slots = [ps[11 + i] for i in range(QUAL_SLOTS)]
    n = len(qual_lines)
    for i in range(min(n, QUAL_SLOTS)):      # 填充已有槽位（自动编号，已带（X）则保留）
        _set_para(qual_slots[i], _numbered(i, qual_lines[i]))
    if n > QUAL_SLOTS:                        # 超出 7 条：克隆末槽位依次插入其后
        prev = qual_slots[-1]
        for i, line in enumerate(qual_lines[QUAL_SLOTS:], start=QUAL_SLOTS):
            new_el = copy.deepcopy(qual_slots[-1]._element)
            prev._element.addnext(new_el)
            new_para = Paragraph(new_el, qual_slots[-1]._parent)
            _set_para(new_para, _numbered(i, line))
            prev = new_para
    else:                                    # 不足 7 条：删除多余空槽位段，避免留空行
        for slot in qual_slots[n:]:
            slot._element.getparent().remove(slot._element)

    # ── 特殊资格要求 二、：模板第 18 段为标题，19/20 为条目样板 ────
    # 每条特殊资格要求各占一段（不足两条删多余样板，多于两条克隆插入）。
    special_text = (ann.special_req or "").strip()
    special_lines = [s.strip() for s in special_text.split("\n") if s.strip()]

    slot1, slot2 = ps[19], ps[20]
    if not special_lines:
        _set_para(slot1, "无。")
        slot2._element.getparent().remove(slot2._element)   # 删除多余样板段
    else:
        _set_para(slot1, _numbered(0, special_lines[0]))
        if len(special_lines) == 1:
            slot2._element.getparent().remove(slot2._element)
        else:
            _set_para(slot2, _numbered(1, special_lines[1]))
            # 第 3 条起：克隆第二个样板段，依次插入其后，各自成段
            prev = slot2
            for i, line in enumerate(special_lines[2:], start=2):
                new_el = copy.deepcopy(slot2._element)
                prev._element.addnext(new_el)
                new_para = Paragraph(new_el, slot2._parent)
                _set_para(new_para, _numbered(i, line))
                prev = new_para

    # ── 报名时间 Para[22] ────────────────────────────────────────
    reg_start = ann.reg_start or "XXXX"
    reg_end = ann.reg_end or "XXXX"
    date_text = f"{reg_start}至{reg_end}（{reg_end}中午12:00截止）"
    _set(ps[22], 3, date_text)
    _clear_from(ps[22], 4)

    # ── 报名备注 Para[23]：run[0]="注：" run[1]=备注正文 ─────────
    reg_note = (ann.reg_note or "").strip()
    if not reg_note:
        reg_note = (
            f"{reg_start}-{reg_end}报名时间"
            f"（上午08时30分至12时00分，下午14时30分至17时00分）。"
        )
    _set(ps[23], 1, reg_note)
    _clear_from(ps[23], 2)

    # ── 获取文件地点 Para[24] ────────────────────────────────────
    agency_addr = ann.agency_address or ""
    delivery_addr = ann.delivery_address or agency_addr
    _set(ps[24], 1, agency_addr)
    _set(ps[24], 3, agency_name)
    _set(ps[24], 4, "竞选文件发售办理处。")

    # ── 代理邮箱 Para[31]: run[5] ────────────────────────────────
    _set(ps[31], 5, ann.agency_email or "")

    # ── 报名咨询电话 Para[32]: run[1] ────────────────────────────
    _set(ps[32], 1, ann.agency_reg_phone or "")

    # ── 响应文件截止时间 Para[35] ────────────────────────────────
    deadline = ann.response_deadline or "XXXX"
    _set(ps[35], 2, deadline + "（北京时间）。")
    _clear_from(ps[35], 3)

    # ── 递交响应文件地点 Para[36] ────────────────────────────────
    _set(ps[36], 2, delivery_addr)
    _set(ps[36], 7, agency_name)

    # ── 代理机构名 Para[44] ──────────────────────────────────────
    _set(ps[44], 4, agency_name)

    # ── 代理地址 Para[45] ────────────────────────────────────────
    _set(ps[45], 1, agency_addr)

    # ── 代理联系人 Para[47] ──────────────────────────────────────
    _set(ps[47], 1, ann.agency_contact or "")

    # ── 代理联系电话 Para[48] ────────────────────────────────────
    _set(ps[48], 1, ann.agency_contact_phone or "")

    # ── 采购人（医院）联系人 Para[42]：随项目经办人变化（姓+老师）──
    # 模板写死「黄老师」，但经办人可能是别人（如郑跃俊→郑老师）。电话 Para[43]
    # 是医院采购部总机，各经办人共用，保持模板值不动。
    officer = (project.officer or "").strip()
    if officer:
        _set(ps[42], 1, f"{officer[0]}老师")

    from services.docx_utils import strip_highlight
    strip_highlight(doc)                 # 清除模板黄色高亮占位印记
    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def get_filename(project, ann):
    suffix = ""
    if ann.round_number and ann.round_number > 1:
        cn = ROUND_CN[min(ann.round_number, len(ROUND_CN) - 1)]
        suffix = f"（第{cn}次）"
    return f"采购公告_{project.number}{suffix}.docx"
