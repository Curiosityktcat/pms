"""docx 通用处理工具。"""
from docx.oxml.ns import qn


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
