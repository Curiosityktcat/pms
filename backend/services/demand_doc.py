# -*- coding: utf-8 -*-
"""采购需求表出稿：成稿文件 ＝ 模板 ＋ 信息。

模板是《2.2内江市第一人民医院采购需求表.docx》按 procurement-doc-templates（pdt）
那套规矩改造出来的；信息就是 PMS 里这条采购需求已经填过的字段——不让人再填一遍。

用户 2026-08-18 的补充：
  「信息 = 固定信息（项目立项的相关信息，比如预算金额、项目名称等等）
          + 非固定信息（根据项目实际需求的信息）」
所以下面的映射分成两块：FIXED 来自立项/项目，FLEX 来自这条需求自己填的。
"""
import datetime
import io
import json
import os
import re

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "templates_docx")
TEMPLATE = os.path.join(TEMPLATE_DIR, "2.2采购需求表.docx")
FIELD_MAP = os.path.join(TEMPLATE_DIR, "2.2采购需求表.fields.json")

# 成稿上的勾选符号。**只用中文字体里有的**：
# ☑(U+2611) 和 ☐(U+2610) 在仿宋/仿宋_GB2312/宋体里根本没有字形，
# 用了它们转 PDF 时整个 run 会回退到西文字体，同一行的中文会跟着一起消失
# （pdt 第三条硬规矩，OPMS 那边实测踩过）。
BOX_ON = "■"
BOX_OFF = "□"
SEP = "　"


def _norm(v):
    """比对前先规整：去掉空白与全角空格。选项文字里常带排版用的空格。"""
    return re.sub(r"[\s　]+", "", str(v or ""))


def _mark(options, chosen):
    """把选项全印出来，选中的打 ■。事后核对时看得出当时有哪些选项可选。

    **只认精确匹配。** 原来还带一层子串兜底（`o in p`），结果
    「分包采购」是「不分包采购」的子串——选了不分包，两个都打上了勾
    （2026-08-19 黄新博实测发现）。互为子串的选项在这张表里不止一处，
    子串匹配是错的，宁可漏勾（一眼看得出来）也不能错勾（盖章发出去才发现）。
    """
    picked = set()
    if isinstance(chosen, (list, tuple, set)):
        picked = {_norm(x) for x in chosen if _norm(x)}
    elif chosen is not None and _norm(chosen):
        picked = {_norm(chosen)}
    out = []
    for o in options:
        o = str(o).strip()
        out.append(f"{BOX_ON if _norm(o) in picked else BOX_OFF} {o}")
    return SEP.join(out)


def _f_yesno(value):
    return _mark(["是", "否"], value)


def _f_choose(value, *options):
    return _mark(options, value)


def _f_multi(value, *options):
    return _mark(options, value)


def register_filters(tpl_env):
    tpl_env.filters["是否"] = _f_yesno
    tpl_env.filters["选"] = _f_choose
    tpl_env.filters["多选"] = _f_multi


def load_fields():
    """模板里有哪些占位符（做界面和自检都要用）。"""
    if not os.path.exists(FIELD_MAP):
        return []
    with io.open(FIELD_MAP, encoding="utf-8") as f:
        return json.load(f)


def _money(v):
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        return ""
    return f"{n:,.2f}" if n else ""


def build_context(d, project=None):
    """把一条采购需求摊成模板要的上下文。

    算得出来的一律不让人填（pdt：金额大写、今天日期、共几家）。
    """
    def g(*names, default=""):
        for n in names:
            v = getattr(d, n, None)
            if v not in (None, "", 0):
                return v
        return default

    try:
        items = json.loads(getattr(d, "items_json", "") or "[]")
    except Exception:                                        # noqa: BLE001
        items = []

    # ── 固定信息：来自立项/项目 ────────────────────────────────────
    ctx = {
        "采购单位": "内江市第一人民医院",
        "编制单位": "内江市第一人民医院",
        "需求科室": g("demand_dept"),
        "归口管理科室": g("manage_dept"),
        "项目名称": g("project_name") or (project.name if project else ""),
        "所属年度": (str(g("year")) or datetime.date.today().strftime("%Y")) + "年",
        "编制时间": g("compile_date") or datetime.date.today().strftime("%Y年%m月%d日"),
        "预算金额": _money(g("budget_amount")),
        "项目所属分类": g("category"),
    }

    # ── 非固定信息：这条需求自己填的 ───────────────────────────────
    ctx.update({
        "项目概况": g("project_overview"),
        "有无关联服务供应商": g("has_related_supplier", default="否"),
        "相关产业发展情况": g("survey_industry"),
        "市场供给情况": g("survey_market"),
        "历史成交情况": g("survey_history"),
        "后续采购情况": g("survey_followup"),
        "其他相关情况": g("survey_other"),

        "采购组织形式": g("org_form"),
        "预算采购方式": g("budget_method"),
        "采购方式": g("procurement_method"),
        "采购方式2": g("procurement_method"),
        "本项目是否单位自行组织采购": g("self_organized", default="是"),
        "采购包划分": g("package_split"),
        "是否属于一签多年项目": g("is_multi_year"),
        "中小企业政策": g("sme_policy"),
        "是否采购环境标识产品": g("is_eco_product"),
        "是否采购节能产品": g("is_energy_save"),
        "项目的采购标的是否包含进口产品": g("has_import_product"),
        "采购标的是否属于政府购买服务": g("is_govt_service"),
        "是否属于政务信息系统项目": g("is_info_system"),
        "是否科研设备采购": g("is_research_equip"),
        "是否属于PPP项目": g("is_ppp", default="否"),

        "预算金额2": _money(g("budget_amount")),
        "最高限价": _money(g("max_price")),
        "评审方法": g("eval_method"),
        "定价方式": g("pricing_method"),
        "是否支持联合体投标": g("allow_consortium"),
        "是否允许合同分包": g("allow_subcontract"),
        "中小企业政策2": g("sme_policy"),

        "合同类型": g("contract_type"),
        "是否为据实结算": g("contract_is_actual"),
        "合同履行期限": g("contract_period"),
        "合同履约地点": g("contract_location"),
        "合同支付约定": g("payment_terms"),
        "验收交付标准和方法": g("acceptance_delivery"),
        "质量保修范围和保修期": g("warranty_terms"),
        "知识产权归属和处理方式": g("ip_terms"),
        "成本补偿和风险分担约定": g("cost_risk_terms"),
        "违约责任与解决争议的方法": g("breach_terms"),
        "合同其他条款": g("other_contract_terms"),

        "验收组织方式": g("acceptance_org"),
        "是否邀请本项目的其他供应商": g("invite_other_supplier"),
        "是否邀请专家": g("invite_expert", default="否"),
        "是否邀请服务对象": g("invite_client", default="否"),
        "是否邀请第三方检测机构": g("invite_third_party", default="否"),
        "履约验收程序": g("acceptance_procedure"),
        "履约验收时间": g("acceptance_time"),
        "验收组织的其他事项": g("acceptance_other"),
        "技术履约验收内容": g("acceptance_tech"),
        "商务履约验收内容": g("acceptance_business"),
        "履约收标准": g("acceptance_standard"),
        "履约验收其他事项": g("acceptance_extra"),

        "本项目是否需要组织风险判断提出处置措施和替代方案": g("need_risk_plan", default="否"),

        # 标的清单：一行一条，行数随项目变
        "标的": [{
            "包号": it.get("package_no") or it.get("包号") or "",
            "编号": it.get("no") or it.get("编号") or "",
            "品目": it.get("catalog") or it.get("品目") or "",
            "标的名称": it.get("name") or it.get("标的名称") or "",
            "单价": _money(it.get("unit_price") or it.get("单价")),
            "数量": it.get("qty") or it.get("数量") or "",
            "计量单位": it.get("unit") or it.get("计量单位") or "",
            "标的金额": _money(it.get("amount") or it.get("标的金额")),
            "允许进口": it.get("import_ok") or it.get("允许进口") or "",
            "节能": it.get("energy") or it.get("节能") or "",
            "环保": it.get("eco") or it.get("环保") or "",
            "功能和质量要求": it.get("spec") or it.get("功能和质量要求") or "",
            "所属行业": it.get("industry") or it.get("所属行业") or "",
            "核心产品": it.get("core") or it.get("核心产品") or "",
        } for it in items],
    })
    return ctx


def _yn(v):
    """院内竞选那张表把是否题存成 0/1，模板要的是「是」「否」。"""
    if v in (1, "1", True, "是"):
        return "是"
    if v in (0, "0", False, "否", None, ""):
        return "否"
    return str(v)


def build_context_internal(d, project=None):
    """院内竞选需求（InternalBidDemand）→ 同一份采购需求表。

    表是同一张（自行采购只是「标绿部分无需填写」），但字段名和政府采购那张
    对不上，是否题还存成了 0/1，所以单独一套映射。
    """
    def g(*names, default=""):
        for n in names:
            v = getattr(d, n, None)
            if v not in (None, "", 0):
                return v
        return default

    try:
        items = json.loads(getattr(d, "items_json", "") or "[]")
    except Exception:                                        # noqa: BLE001
        items = []

    ctx = {
        "采购单位": "内江市第一人民医院",
        "编制单位": "内江市第一人民医院",
        "需求科室": g("demand_dept"),
        "归口管理科室": g("manage_dept"),
        "项目名称": g("project_name") or (project.name if project else ""),
        "所属年度": (str(g("year")) or datetime.date.today().strftime("%Y")) + "年",
        "编制时间": g("compile_date") or datetime.date.today().strftime("%Y年%m月%d日"),
        "预算金额": _money(g("budget_amount")),
        "项目所属分类": g("category"),
        "项目概况": g("overview"),
        "有无关联服务供应商": _yn(getattr(d, "has_consultant", 0)),

        # 自行采购：3.1 固定「自行采购」，具体方式落在 3.2.3
        "采购组织形式": "自行采购",
        "采购方式2": g("proc_method"),
        "本项目是否单位自行组织采购": "是",
        "采购包划分": g("pkg_split"),
        "是否属于一签多年项目": _yn(getattr(d, "multi_year", 0)),

        "合同类型": g("contract_type"),
        "是否为据实结算": _yn(getattr(d, "actual_settlement", 0)),
        "合同履行期限": g("contract_period"),
        "合同履约地点": g("contract_location"),
        "合同支付约定": g("payment_terms"),
        "验收交付标准和方法": g("acceptance_standard"),
        "质量保修范围和保修期": g("warranty"),
        "知识产权归属和处理方式": g("ip_ownership"),
        "成本补偿和风险分担约定": g("cost_risk"),
        "违约责任与解决争议的方法": g("breach_dispute"),
        "合同其他条款": g("contract_other"),
        "成交供应商是否需要缴纳履约保证金": _yn(getattr(d, "perf_bond", 0)),
        "履约保证金缴纳比例": g("perf_bond_ratio"),
        "缴纳方式": g("perf_bond_method"),
        "缴纳说明": g("perf_bond_note"),
        "成交供应商是否需要缴纳质量保证金": _yn(getattr(d, "quality_bond", 1)),

        "验收组织方式": g("accept_org"),
        "是否邀请本项目的其他供应商": _yn(getattr(d, "invite_supplier", 0)),
        "是否邀请专家": _yn(getattr(d, "invite_expert", 0)),
        "是否邀请服务对象": _yn(getattr(d, "invite_service", 0)),
        "是否邀请第三方检测机构": _yn(getattr(d, "invite_third", 0)),
        "履约验收程序": g("accept_procedure"),
        "履约验收时间": g("accept_time"),
        "验收组织的其他事项": g("accept_other"),
        "技术履约验收内容": g("tech_accept"),
        "商务履约验收内容": g("biz_accept"),
        "履约收标准": g("accept_std"),
        "履约验收其他事项": g("accept_other2"),

        # 政府采购才填的那些，自行采购留空（模板上本来就标绿说明无需填写）
        "本项目是否需要组织风险判断提出处置措施和替代方案": "否",

        "标的": [{
            "包号": it.get("package_no") or it.get("包号") or "",
            "编号": it.get("no") or it.get("编号") or "",
            "品目": it.get("catalog") or it.get("品目") or "",
            "标的名称": it.get("name") or it.get("标的名称") or "",
            "单价": _money(it.get("unit_price") or it.get("单价")),
            "数量": it.get("qty") or it.get("数量") or "",
            "计量单位": it.get("unit") or it.get("计量单位") or "",
            "标的金额": _money(it.get("amount") or it.get("标的金额")),
            "允许进口": it.get("import_ok") or it.get("允许进口") or "",
            "节能": it.get("energy") or it.get("节能") or "",
            "环保": it.get("eco") or it.get("环保") or "",
            "功能和质量要求": it.get("spec") or it.get("功能和质量要求") or "",
            "所属行业": it.get("industry") or it.get("所属行业") or "",
            "核心产品": it.get("core") or it.get("核心产品") or "",
        } for it in items],
    }
    return ctx


def build_context_for(d, project=None):
    """按记录来自哪张表选映射。"""
    if d.__class__.__name__ == "InternalBidDemand":
        return build_context_internal(d, project)
    return build_context(d, project)


def missing_fields(ctx):
    """哪些占位符还空着——界面上要能点回去补。"""
    out = []
    for f in load_fields():
        if f["kind"] == "table":
            if not ctx.get(f["name"]):
                out.append(f)
            continue
        v = ctx.get(f["name"])
        if v in (None, "", []):
            out.append(f)
    return out


# 一份文书一份字典。政府采购和院内竞选**共用同一张 Word 模板**，
# 但规则完全不同（政采只能分散采购、只能用政采那六种方式；院内竞选是自行采购、
# 走院内竞选/议价/询价）。把政采的字典套到院内竞选上，会把它的选项全清掉——
# 2026-08-19 加字典时当场撞到，验收脚本报的就是这个。
DICT_BY_MODEL = {
    "ProcurementDemand": "2.2采购需求表",
    # 院内竞选的规则还没定，先不套字典（套一份错的比不套更糟）
    "InternalBidDemand": None,
}


def dict_name_for(d):
    return DICT_BY_MODEL.get(d.__class__.__name__, "2.2采购需求表")


def apply_dict(ctx, dict_name="2.2采购需求表"):
    """出稿前把字典规则套一遍：锁定的纠正回来、隐藏的清掉、选项带出的值补上。

    为什么放在出稿这一步而不是只放界面：界面能绕过（改请求、老数据、导入的 Excel），
    而这是要盖章对外发的文件。**成稿以字典为准**，这条不能只靠前端自觉。
    """
    if not dict_name:
        return ctx, {}
    from services import field_dict as fd
    fields = fd.load(dict_name)
    if not fields:
        return ctx, {}
    eff, meta = fd.resolve(fields, ctx)
    merged = dict(ctx)
    merged.update(eff)
    # 字典说不显示的，成稿里也不能留上一轮的残值
    for name, m in meta.items():
        if not m.get("visible", True):
            merged[name] = ""
    return merged, meta


def render(d, project=None):
    """出稿，返回 (BytesIO, 缺的字段列表)。"""
    from docxtpl import DocxTemplate
    if not os.path.exists(TEMPLATE):
        raise FileNotFoundError(f"模板不在：{TEMPLATE}")
    ctx = build_context_for(d, project)
    ctx, _meta = apply_dict(ctx, dict_name_for(d))
    tpl = DocxTemplate(TEMPLATE)
    env = tpl.get_undeclared_template_variables  # 触发 jinja env 初始化
    from jinja2 import Environment
    jenv = Environment()
    register_filters(jenv)
    tpl.render(ctx, jenv)
    buf = io.BytesIO()
    tpl.save(buf)
    buf.seek(0)
    return buf, missing_fields(ctx)
