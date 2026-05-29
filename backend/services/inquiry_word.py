"""
生成询/议价邀请函 Word 文档（python-docx）
"""
from io import BytesIO
import datetime

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT


def generate_inquiry_word(letter, project_name: str, project_number: str) -> BytesIO:
    """
    letter: InquiryLetter 对象（或含相应属性的 dict-like）
    返回包含 Word 文档内容的 BytesIO 对象
    """
    doc = Document()

    # ── 页面边距 ──────────────────────────────────────────────────
    for section in doc.sections:
        section.top_margin    = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin   = Cm(3.0)
        section.right_margin  = Cm(2.5)

    # ── 主标题 ────────────────────────────────────────────────────
    letter_type = getattr(letter, "type", "询价")
    title_text = f"内江市第一人民医院{letter_type}邀请函"
    title_para = doc.add_paragraph()
    title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title_run = title_para.add_run(title_text)
    title_run.font.size = Pt(16)
    title_run.font.bold = True
    title_run.font.color.rgb = RGBColor(0x1F, 0x34, 0x64)

    # ── 副标题（函件标题）──────────────────────────────────────────
    letter_title = getattr(letter, "title", "")
    if letter_title:
        sub_para = doc.add_paragraph()
        sub_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sub_run = sub_para.add_run(letter_title)
        sub_run.font.size = Pt(11)
        sub_run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)

    doc.add_paragraph()  # 空行

    # ── 项目基本信息表格 ──────────────────────────────────────────
    info_table = doc.add_table(rows=3, cols=2)
    info_table.alignment = WD_TABLE_ALIGNMENT.CENTER
    info_table.style = "Table Grid"

    cells = [
        ("项目名称", project_name or "—"),
        ("项目编号", project_number or "—"),
        ("函件类型", f"{letter_type}（{'竞争性询价，3家及以上供应商' if letter_type == '询价' else '议价，1-2家供应商'}）"),
    ]
    for i, (label, val) in enumerate(cells):
        row = info_table.rows[i]
        row.cells[0].text = label
        row.cells[1].text = val
        for cell in row.cells:
            for para in cell.paragraphs:
                for run in para.runs:
                    run.font.size = Pt(10.5)
        # 标签列宽
        row.cells[0].width = Cm(3)

    doc.add_paragraph()  # 空行

    # ── 正文内容 ──────────────────────────────────────────────────
    content = getattr(letter, "content", "")
    if content:
        for line in content.split("\n"):
            para = doc.add_paragraph()
            para.paragraph_format.first_line_indent = Pt(21)  # 首行缩进 2 字符
            run = para.add_run(line)
            run.font.size = Pt(11)

    doc.add_paragraph()  # 空行

    # ── 截止日期 ──────────────────────────────────────────────────
    deadline = getattr(letter, "deadline", "")
    if deadline:
        deadline_para = doc.add_paragraph()
        deadline_para.paragraph_format.left_indent = Cm(0)
        dr = deadline_para.add_run(f"请于 {deadline} 前回复报价。")
        dr.font.size = Pt(11)
        dr.font.bold = True
        dr.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)

    doc.add_paragraph()  # 空行

    # ── 落款 ──────────────────────────────────────────────────────
    sign_para = doc.add_paragraph()
    sign_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    sign_run = sign_para.add_run("内江市第一人民医院采购部")
    sign_run.font.size = Pt(11)
    sign_run.font.bold = True

    date_para = doc.add_paragraph()
    date_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    today = datetime.date.today()
    date_run = date_para.add_run(f"{today.year}年{today.month}月{today.day}日")
    date_run.font.size = Pt(11)

    # ── 备注 ──────────────────────────────────────────────────────
    notes = getattr(letter, "notes", "")
    if notes:
        doc.add_paragraph()
        note_para = doc.add_paragraph()
        note_run = note_para.add_run(f"备注：{notes}")
        note_run.font.size = Pt(10)
        note_run.font.color.rgb = RGBColor(0x88, 0x88, 0x88)

    # ── 保存到内存 ────────────────────────────────────────────────
    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf
