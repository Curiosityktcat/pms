import io
import os
from docx import Document

TEMPLATE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..",
    "医院模板", "文件汇总", "1.（打印1份盖章）《院内竞选文件》内容确认表（第xx次）.docx"
))


def _set_cell_text(table, row, col, text):
    """完全替换单元格文本（保留单元格本身格式）。"""
    try:
        table.cell(row, col).text = text
    except Exception:
        pass


def _category_str(category):
    cats = ["货物", "服务", "工程"]
    return "".join(("☑" if category == c else "□") + c for c in cats)


def generate(project, agency_name):
    """按模板生成《院内竞选文件》内容确认表，返回 (BytesIO, filename)。

    填充：项目名称、采购编号、项目内容(分类勾选)、代理机构、采购方式。
    其余（联系人/哈希值/审核日期/盖章）留空，人工填写。
    """
    doc = Document(TEMPLATE)
    t = doc.tables[0]

    pname = (project.name or "").strip()
    pnumber = (project.number or "").strip()

    _set_cell_text(t, 0, 1, pname)                              # 项目名称（合并单元格）
    _set_cell_text(t, 1, 1, pnumber)                            # 采购编号
    _set_cell_text(t, 1, 3, _category_str(project.category))    # 项目内容（货物/服务/工程）
    _set_cell_text(t, 2, 1, (agency_name or "").strip())        # 代理机构
    _set_cell_text(t, 4, 3, (project.method or "院内竞选").strip())  # 采购方式

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    filename = f"内容确认表_{pnumber or pname or '确认表'}.docx"
    return buf, filename
