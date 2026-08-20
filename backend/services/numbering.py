"""
编号生成服务 —— 逻辑直接从 numbering.py 移植，接口不变。
唯一差异：gen_number() 不再接收 sqlite3 连接，改用 SQLAlchemy db.session。
"""
import datetime
from sqlalchemy import text
from models import db

M_YIJIA  = "院内议价"
M_XUNJIA = "院内询价"
M_JINGXUAN = "院内竞选"
M_SOLE   = "院内单一来源采购"
M_JINGJI = "医用耗材紧急采购"   # 不分金额、不走代理


# 走不走代理由经办人选择的采购方式。两者的默认值相反：
#   单一来源——院内自办是常态，不选 = 不走代理
#   竞选——99% 的项目都委托代理机构，不选 = 走代理
CHOICE_AGENCY_METHODS = (M_SOLE, M_JINGXUAN)


def parse_agency_choice(method, raw):
    """把表单值解析成 decide() 要的三态 use_agency 选择。

    raw 取自 use_agency / sole_use_agency 字段（"yes" / "no" / 空）。
    返回 True=走代理、False=不走代理、None=该方式不由用户选。
    """
    v = (raw or "").strip()
    if method == M_SOLE:
        return v == "yes"        # 默认不走代理
    if method == M_JINGXUAN:
        return v != "no"         # 默认走代理
    return None


def decide(method, amount=None, is_unit_price=False, sole_use_agency=None):
    """返回 (use_agency: bool, line: 'A'/'B'/'C')

    sole_use_agency 是「是否走代理」的选择（历史字段名，现在竞选也用它）：
    True=走代理、False=不走代理、None=没给（按该方式的默认值）。
    """
    # 单一来源、紧急采购、竞选是人工明确选定的采购方式，走不走代理由方式本身
    # （或用户的选择）决定，不能被「招单价」翻成走代理——否则「单一来源+不走
    # 代理」会被要求选代理机构而立不了项。
    if method == M_SOLE:
        if sole_use_agency:
            return True, "C"
        if not is_unit_price and amount is not None and amount < 20000:
            return False, "A"
        return False, "B"
    if method == M_JINGJI:
        return False, "A"   # 不分金额、不走代理，线 A
    if method == M_JINGXUAN:
        # 没给选择时按老口径走代理；明确选了不走代理才院内自办，线 B
        return (True, "C") if (sole_use_agency is None or sole_use_agency) else (False, "B")
    if is_unit_price:
        return True, "C"
    if method == M_YIJIA:
        return False, "A"
    if method == M_XUNJIA:
        return False, "B"
    # 兜底按金额
    if amount is None:
        return True, "C"
    if amount < 20000:
        return False, "A"
    if amount < 50000:
        return False, "B"
    return True, "C"


def gen_number(use_agency, agency_code=None, when=None):
    """原子地递增序号并返回编号字符串。必须在 Flask 请求上下文中调用。"""
    if use_agency and not agency_code:
        raise ValueError("走代理机构的项目必须指定代理机构")
    now = when or datetime.datetime.now()
    ym = now.strftime("%y%m")
    kind = "JX" if use_agency else "XJ"
    db.session.execute(
        text("INSERT OR IGNORE INTO number_seq(kind, ym, seq) VALUES(:kind, :ym, 0)"),
        {"kind": kind, "ym": ym},
    )
    db.session.execute(
        text("UPDATE number_seq SET seq = seq + 1 WHERE kind = :kind AND ym = :ym"),
        {"kind": kind, "ym": ym},
    )
    row = db.session.execute(
        text("SELECT seq FROM number_seq WHERE kind = :kind AND ym = :ym"),
        {"kind": kind, "ym": ym},
    ).fetchone()
    seq = row[0]
    if use_agency:
        return f"NJYYJX-{agency_code}-{ym}{seq:03d}"
    return f"NJYYXJ-{ym}{seq:03d}"
