"""docx 通用处理工具。"""
from docx.oxml.ns import qn


def set_default_fonts(doc, east_asia="仿宋_GB2312", latin="Times New Roman"):
    """把文档 Normal 样式默认字体设为公文体：中文仿宋、西文 Times New Roman。

    对从零生成（Document()）的文档调用一次即可，正文 run 不再逐个设字体；
    个别标题仍可按需覆盖（如黑体）。"""
    style = doc.styles["Normal"]
    style.font.name = latin           # 设 ascii/hAnsi，并确保 rPr/rFonts 存在
    style.element.rPr.rFonts.set(qn("w:eastAsia"), east_asia)
    return doc


def _remove_highlight_in(element):
    """删除某 XML 元素下所有 run 级高亮（<w:highlight>，模板里多为黄色占位印记）。"""
    if element is None:
        return
    for hl in list(element.iter(qn("w:highlight"))):
        parent = hl.getparent()
        if parent is not None:
            parent.remove(hl)


def strip_highlight(doc):
    """清除整个文档（正文/表格 + 页眉页脚）里的荧光高亮印记。无高亮时为安全空操作。"""
    _remove_highlight_in(doc.element.body)
    for section in doc.sections:
        for hf in (
            section.header, section.first_page_header, section.even_page_header,
            section.footer, section.first_page_footer, section.even_page_footer,
        ):
            try:
                _remove_highlight_in(hf._element)
            except Exception:
                pass
    return doc
