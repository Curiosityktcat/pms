"""采购文件「AI 编制建议」服务（Phase 2）。

把项目的采购需求结构化数据组装成摘要，交给大模型，以「医用耗材院内竞选
采购文件审阅专家」的身份输出意见和建议（纯文字，供经办人/代理参考，不改文档、
不定稿）。模型调用走全系统共用的 services.llm_client。

用法（须在 Flask app 上下文内）：
    from services.procurement_doc_ai import review
    text = review(project, demand)
"""
import json

from services.llm_client import chat, get_llm_config

SYSTEM_PROMPT = """你是内江市第一人民医院「院内竞选」采购文件编制的资深审阅专家，尤其熟悉医用耗材类采购。
我会给你某个采购项目已填写的「采购需求」信息。请你站在审阅者角度，对照采购文件编制要求，给出具体、可操作的意见和建议。

严格遵守：
1. 只依据我提供的信息判断，绝对不要编造预算、参数、品牌等事实；原文没写的，明确指出「缺失/未填写」，不要替它臆造内容。
2. 建议要具体、能落地（指出是哪一项、改成什么、为什么），不要泛泛而谈。
3. 用中文，按下面的结构输出 Markdown，每节只写有内容可说的要点，没有问题的节可写「未发现明显问题」：

## 一、完整性检查
（技术要求、商务要求、资格要求、评分办法、合同条款、验收标准等关键要素是否齐全；缺哪项点名）

## 二、合规与风险提示
（是否有指向性/排他性参数、以不合理条件限制供应商、评分设置不当、违反公平竞争等风险）

## 三、技术参数建议
（针对医用耗材的规格、注册证/许可、技术指标是否清晰可量化、是否便于客观评审）

## 四、评分办法建议
（评审方式、价格分与技术分配比、各项评分标准是否客观可操作）

## 五、商务与合同建议
（付款方式、履约期限、质保、违约责任、验收标准等是否明确、是否保护采购人利益）

## 六、总体结论
（一句话总体评价 + 最优先处理的 2~3 条）
"""


def _fmt(value):
    """非空且非零值返回字符串，否则返回 None（不纳入摘要）。"""
    if value is None:
        return None
    s = str(value).strip()
    if not s or s in ("0", "0.0", "[]"):
        return None
    return s


def _section(title, rows):
    """rows 为 (label, value) 列表；过滤空值，全空则返回 None。"""
    items = [f"- {label}：{v}" for label, value in rows if (v := _fmt(value))]
    if not items:
        return None
    return f"【{title}】\n" + "\n".join(items)


def build_demand_summary(demand, project=None):
    """把采购需求结构化字段整理成可读摘要文本（只含已填写项）。"""
    sections = []

    sections.append(_section("项目基本信息", [
        ("项目名称", demand.project_name or (project.name if project else "")),
        ("所属年度", demand.year),
        ("项目分类", demand.category),
        ("预算金额(元)", f"{demand.budget_amount:.2f}" if demand.budget_amount else ""),
        ("项目概况", demand.project_overview),
        ("采购方式", demand.procurement_method),
        ("采购包划分", demand.package_split),
        ("是否一签多年", demand.is_multi_year),
        ("最高限价(元)", f"{demand.max_price:.2f}" if demand.max_price else ""),
    ]))

    # 标的明细
    try:
        items = json.loads(demand.items_json or "[]")
    except Exception:
        items = []
    if items:
        rows = []
        for i, it in enumerate(items, 1):
            parts = [
                it.get("name", ""), it.get("category", ""),
                f"数量{it.get('quantity', '')}{it.get('unit', '')}".strip(),
                f"单价{it.get('unit_price', '')}" if it.get("unit_price") else "",
                it.get("requirements", ""),
            ]
            rows.append(f"  {i}. " + " / ".join(p for p in parts if p))
        sections.append("【采购标的明细】\n" + "\n".join(rows))

    sections.append(_section("技术与资格要求", [
        ("技术要求", demand.tech_requirements),
        ("商务要求", demand.business_requirements),
        ("资格要求", demand.qualification_requirements),
    ]))
    sections.append(_section("评审办法", [
        ("评审方式", demand.eval_method),
        ("价格分值", demand.eval_price_score),
        ("技术评分标准", demand.eval_tech_criteria),
        ("服务评分标准", demand.eval_service_criteria),
    ]))
    sections.append(_section("合同与验收", [
        ("合同类型", demand.contract_type),
        ("履约期限", demand.contract_period),
        ("支付约定", demand.payment_terms),
        ("质量保修", demand.warranty_terms),
        ("违约责任", demand.breach_terms),
        ("验收程序", demand.acceptance_procedure),
        ("技术验收内容", demand.acceptance_tech),
        ("商务验收内容", demand.acceptance_biz),
        ("验收标准", demand.acceptance_standard),
    ]))

    return "\n\n".join(s for s in sections if s).strip()


def review(project, demand, *, max_tokens=3000, usage_ctx=None):
    """调用大模型，返回审阅意见 Markdown 文本。
    usage_ctx 传入时按账号记录 token 用量。"""
    summary = build_demand_summary(demand, project)
    user = (
        "以下是该采购项目已填写的采购需求信息，请审阅并给出意见和建议：\n\n"
        f"{summary}\n"
    )
    return chat(SYSTEM_PROMPT, user, temperature=0.4, max_tokens=max_tokens,
                timeout=240, usage_ctx=usage_ctx)


def current_model_name():
    """返回当前使用的模型名，便于前端展示。"""
    try:
        return get_llm_config().get("name", "")
    except Exception:
        return ""
