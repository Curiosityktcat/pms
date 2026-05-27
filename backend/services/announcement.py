"""
采购公告生成服务
"""
import io
import os
from docx import Document
from models.announcement import QUAL_DEFAULTS

TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "医院模板", "1.盖章文件", "采购公告.docx",
)

ROUND_CN = ["", "一", "二", "三", "四", "五"]


def _r(para, idx):
    """安全获取 run，越界返回 None。"""
    runs = para.runs
    if idx < len(runs):
        return runs[idx]
    return None


def _set(para, idx, text):
    r = _r(para, idx)
    if r is not None:
        r.text = text


def _clear_from(para, start_idx):
    for i in range(start_idx, len(para.runs)):
        para.runs[i].text = ""


def _set_para_full(para, text: str):
    """用第一个 run 写入全文，其余 run 清空。保留字体格式。"""
    runs = para.runs
    if not runs:
        return
    runs[0].text = text
    for r in runs[1:]:
        r.text = ""


def generate(project, ann, agency_name):
    """
    生成采购公告 Word 文档，返回 BytesIO。

    project: Project model 实例
    ann: Announcement model 实例
    agency_name: 代理机构名称字符串
    """
    doc = Document(TEMPLATE_PATH)
    ps = doc.paragraphs

    project_name = project.name or ""
    project_number = project.number or ""

    # ── 标题 Para[0] ──────────────────────────────────────────────
    _set(ps[0], 1, "")
    _set(ps[0], 2, project_name)
    _set(ps[0], 3, "院内竞选公告")

    # ── 正文 Para[2] ──────────────────────────────────────────────
    _set(ps[2], 0, agency_name)
    _set(ps[2], 4, project_name)

    # ── 项目编号 Para[3]: run[2] ──────────────────────────────────
    _set(ps[3], 2, project_number + "；")

    # ── 项目名称 Para[4]: run[2] ──────────────────────────────────
    _set(ps[4], 2, project_name + "；")

    # ── 招标项目简介 Para[6]: run[0] ────────────────────────────
    _set(ps[6], 0, ann.project_intro or "")

    # ── 一般资格要求 Para[11-16]：每段单 run，直接替换 ───────────
    quals = [
        ann.qual_1 or QUAL_DEFAULTS[0],
        ann.qual_2 or QUAL_DEFAULTS[1],
        ann.qual_3 or QUAL_DEFAULTS[2],
        ann.qual_4 or QUAL_DEFAULTS[3],
        ann.qual_5 or QUAL_DEFAULTS[4],
        ann.qual_6 or QUAL_DEFAULTS[5],
    ]
    for i, q_text in enumerate(quals):
        p = ps[11 + i]
        if p.runs:
            p.runs[0].text = q_text
            for r in p.runs[1:]:
                r.text = ""

    # ── 特殊要求（七）Para[17]: run[0] ──────────────────────────
    if ann.special_req:
        _set(ps[17], 0, "（七）" + ann.special_req)

    # ── 报名时间 Para[22] ────────────────────────────────────────
    reg_start = ann.reg_start or "XXXX"
    reg_end = ann.reg_end or "XXXX"
    date_text = f"{reg_start}至{reg_end}（{reg_end}中午12:00截止）"
    _set(ps[22], 3, date_text)
    _clear_from(ps[22], 4)

    # ── 报名备注 Para[23]：run[0]="注：" run[1]=备注正文 ─────────
    reg_note = (ann.reg_note or "").strip()
    if not reg_note:
        # 自动生成默认备注
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

    # ── 代理机构名 Para[44]: run[4] ──────────────────────────────
    _set(ps[44], 4, agency_name)

    # ── 代理地址 Para[45]: run[1] ────────────────────────────────
    _set(ps[45], 1, agency_addr)

    # ── 代理联系人 Para[47]: run[1] ──────────────────────────────
    _set(ps[47], 1, ann.agency_contact or "")

    # ── 代理联系电话 Para[48]: run[1] ────────────────────────────
    _set(ps[48], 1, ann.agency_contact_phone or "")

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def get_filename(project, ann):
    """生成下载文件名。"""
    suffix = ""
    if ann.round_number and ann.round_number > 1:
        cn = ROUND_CN[min(ann.round_number, len(ROUND_CN) - 1)]
        suffix = f"（第{cn}次）"
    return f"采购公告_{project.number}{suffix}.docx"
