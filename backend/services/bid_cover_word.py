import io
import os
from docx import Document

TEMPLATE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "医院模板", "1.盖章文件", "2.（打印2份盖章）招标文件封面（第xx次）.docx"
))

_CN_NUM = "一二三四五六七八九十"


def _round_cn(n):
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if 1 <= n <= 10:
        return _CN_NUM[n - 1]
    return str(n)


def _set_para_text(paragraph, new_text):
    """整段替换文本，保留首个 run 的格式（字号/居中等），清空其余 run。"""
    runs = paragraph.runs
    if not runs:
        return
    runs[0].text = new_text
    for r in runs[1:]:
        r.text = ""


def generate(project, agency_name, *, compile_date="", round_number=1):
    """按模板生成《院内竞选文件》招标文件封面，返回 (BytesIO, filename)。"""
    doc = Document(TEMPLATE)

    pname = (project.name or "").strip()
    rn = round_number or project.round or 1
    if rn and int(rn) > 1:
        suffix = f"（第{_round_cn(rn)}次）"
        if suffix not in pname:
            pname += suffix
    pnumber = (project.number or "").strip()

    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue
        if t.startswith("采购项目名称："):
            _set_para_text(p, f"采购项目名称：{pname}")
        elif t.startswith("采购项目编号："):
            _set_para_text(p, f"采购项目编号：{pnumber}")
        elif "共同编制" in t:
            _set_para_text(p, f"{agency_name}共同编制")
        elif "202" in t and "年" in t and "日" in t:
            if compile_date:
                _set_para_text(p, compile_date)

    buf = io.BytesIO()
    from services.docx_utils import strip_highlight
    strip_highlight(doc)                 # 清除模板黄色高亮占位印记
    doc.save(buf)
    buf.seek(0)
    filename = f"招标文件封面_{pnumber or pname or '封面'}.docx"
    return buf, filename
