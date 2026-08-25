# -*- coding: utf-8 -*-
"""采购需求“在成稿上填”的文档结构。

这里只负责把现有成稿上下文、字段字典和字段归属拼成前端可渲染的数据；
不复制字段规则，也不负责保存。下一步 PDT encode 可以直接按 ``class_name``
把带 class 的 span 写回同一条字段路径。
"""
import json
import re

from services import demand_doc, field_dict


SECTIONS = (
    ("population", "一、项目总体情况", (
        "项目名称", "采购单位", "需求科室", "归口管理科室", "所属年度", "编制时间",
        "项目所属分类", "预算金额", "项目概况", "有无关联服务供应商",
    )),
    ("survey", "二、需求调查情况", (
        "需求调查是否需要", "相关产业发展情况", "市场供给情况", "历史成交情况",
        "后续采购情况", "其他相关情况",
    )),
    ("implementation", "三、采购实施计划", (
        "采购组织形式", "采购方式", "本项目是否单位自行组织采购", "采购包划分",
        "是否属于一签多年项目", "中小企业政策", "是否采购环境标识产品",
        "是否采购节能产品", "项目的采购标的是否包含进口产品",
        "采购标的是否属于政府购买服务", "是否属于政务信息系统项目",
        "是否科研设备采购", "是否属于PPP项目", "标的",
    )),
    ("subcontract", "四、采购包、合同与履约验收", (
        "合同类型", "是否为据实结算", "合同履行期限", "合同履约地点",
        "合同支付约定", "验收交付标准和方法", "质量保修范围和保修期",
        "知识产权归属和处理方式", "成本补偿和风险分担约定",
        "违约责任与解决争议的方法", "合同其他条款", "验收组织方式",
        "是否邀请本项目的其他供应商", "是否邀请专家", "是否邀请服务对象",
        "是否邀请第三方检测机构", "履约验收程序", "履约验收时间",
        "验收组织的其他事项", "技术履约验收内容", "商务履约验收内容",
        "履约收标准", "履约验收其他事项",
    )),
    ("risk", "五、风险控制", (
        "本项目是否需要组织风险判断提出处置措施和替代方案",
    )),
)


# 中文模板字段到既有 ProcurementDemand 列；保存仍走原 PUT 接口。
FIELD_TO_COLUMN = {
    # 第一部分那几项：表里印着，模型上也有列，原来就是没接上来，
    # 结果界面上填不了（黄新博 2026-08-25 实测「只需要填4个地方」）。
    "项目名称": "project_name", "需求科室": "demand_dept",
    "归口管理科室": "manage_dept", "所属年度": "year",
    "项目所属分类": "category", "预算金额": "budget_amount",
    "项目概况": "project_overview", "有无关联服务供应商": "has_related_supplier",
    "需求调查是否需要": "survey_needed", "相关产业发展情况": "survey_industry",
    "市场供给情况": "survey_market", "历史成交情况": "survey_history",
    "后续采购情况": "survey_followup", "其他相关情况": "survey_other",
    "采购组织形式": "org_form", "采购方式": "procurement_method",
    "采购包划分": "package_split", "是否属于一签多年项目": "is_multi_year",
    "中小企业政策": "sme_policy", "是否采购环境标识产品": "is_eco_product",
    "是否采购节能产品": "is_energy_save",
    "项目的采购标的是否包含进口产品": "has_import_product",
    "采购标的是否属于政府购买服务": "is_govt_service",
    "是否属于政务信息系统项目": "is_info_system", "是否科研设备采购": "is_research_equip",
    "合同类型": "contract_type", "是否为据实结算": "contract_is_actual",
    "合同履行期限": "contract_period", "合同履约地点": "contract_location",
    "合同支付约定": "payment_terms", "验收交付标准和方法": "acceptance_delivery",
    "质量保修范围和保修期": "warranty_terms", "知识产权归属和处理方式": "ip_terms",
    "成本补偿和风险分担约定": "cost_risk_terms",
    "违约责任与解决争议的方法": "breach_terms", "合同其他条款": "other_contract_terms",
    "验收组织方式": "acceptance_org", "是否邀请本项目的其他供应商": "invite_other_supplier",
    "是否邀请专家": "invite_expert", "是否邀请服务对象": "invite_service_obj",
    "是否邀请第三方检测机构": "invite_third_party", "履约验收程序": "acceptance_procedure",
    "履约验收时间": "acceptance_time", "验收组织的其他事项": "acceptance_misc",
    "技术履约验收内容": "acceptance_tech", "商务履约验收内容": "acceptance_biz",
    "履约收标准": "acceptance_standard", "履约验收其他事项": "acceptance_extra",
    "本项目是否需要组织风险判断提出处置措施和替代方案": "risk_needed",
}

# 只有这两个不给人填：采购单位是固定值，编制时间出稿时按当天算。
# 其余原来都在这儿挂着「上游带入」的名义锁死，可立项时上游还没有值，
# 表里印着一行、界面上却没地方填（黄新博 2026-08-25 实测只剩 4 处可填）。
UPSTREAM = {
    "采购单位", "编制时间",
}

REQUIRED = {
    "项目概况", "有无关联服务供应商", "采购方式", "采购包划分", "中小企业政策",
    "合同履行期限", "合同履约地点", "合同支付约定", "验收交付标准和方法",
    "质量保修范围和保修期", "履约验收程序", "履约验收时间",
}

LONG_TEXT = {
    "项目概况", "相关产业发展情况", "市场供给情况", "历史成交情况", "后续采购情况",
    "其他相关情况", "中小企业政策", "合同支付约定", "验收交付标准和方法",
    "质量保修范围和保修期", "知识产权归属和处理方式", "成本补偿和风险分担约定",
    "违约责任与解决争议的方法", "合同其他条款", "履约验收程序",
    "验收组织的其他事项", "技术履约验收内容", "商务履约验收内容",
    "履约收标准", "履约验收其他事项",
}

PACKAGE_SIMPLE = (
    ("预算金额", "预算金额", "number", True),
    ("最高限价", "最高限价", "number", True),
    ("评审方法", "评审方法", "choice", True),
    ("定价方式", "定价方式", "choice", True),
    ("是否支持联合体投标", "是否支持联合体投标", "choice", True),
    ("是否允许合同分包", "是否允许合同分包", "choice", True),
    # 表里 4.x.6 / 4.x.7 一直没做，出稿时这两行永远是空的
    ("中小企业政策", "执行政府采购促进中小企业发展的相关政策", "choice", True),
    ("是否适用本国产品标准", "是否适用本国产品标准", "choice", True),
)

PACKAGE_PATH = {
    "中小企业政策": "smePolicy", "是否适用本国产品标准": "domesticStandard",
    "标的": "packageItems",
    "预算金额": "budgetAmount", "最高限价": "maxPrice", "评审方法": "evaluationMethod",
    "定价方式": "pricingMethod", "是否支持联合体投标": "allowConsortium",
    "是否允许合同分包": "allowSubcontract", "技术要求": "technicalRequirements",
    "商务要求": "businessRequirements", "一般资格要求": "generalQualifications",
    "特殊资格要求": "specialQualifications", "评审因素": "evaluationFactors",
}


def _camel(value):
    parts = str(value or "").split("_")
    return parts[0] + "".join(x[:1].upper() + x[1:] for x in parts[1:])


def _label(field, fallback):
    """原样返回表里的标签，**编号不剥**——表上印着 1.6，界面就显示 1.6，
    不然填的人得自己数到第几项才知道对应表上哪一行。"""
    return str((field or {}).get("label") or fallback).strip() or fallback



# 表里 4.x 这一段的编号和文字，照 政府采购需求表.docx 抄的。
# 「最高限价」表上跟预算金额挤在 4.x.1 同一行，所以共用编号；
# 「商务要求」在表上没有独立编号（它是技术参数表里的一行），留空退回包名写法。
PACKAGE_LABELS = {
    "预算金额": "{n}.1预算金额（元）",
    "最高限价": "{n}.1最高限价（元）",
    "评审方法": "{n}.2评审方法",
    "定价方式": "{n}.3定价方式",
    "是否支持联合体投标": "{n}.4是否支持联合体投标",
    "是否允许合同分包": "{n}.5是否允许合同分包选项",
    "中小企业政策": "{n}.6执行政府采购促进中小企业发展的相关政策",
    "是否适用本国产品标准": "{n}.7是否适用本国产品标准",
    "标的": "{n}.8标的具体情况",
    "技术要求": "{n}.9技术参数要求",
    "一般资格要求": "{n}.10供应商一般资格要求",
    "特殊资格要求": "{n}.11供应商特殊资格要求",
    "评审因素": "{n}.12分包的评审条款",
}


def _pkg_label(definition, fallback, index, package_name, name=None):
    """包内标签按表上的编号显示，比如「4.1.6执行政府采购促进中小企业发展的相关政策」。"""
    tpl = PACKAGE_LABELS.get(name or fallback)
    if tpl:
        return tpl.format(n="4.%d" % (index + 1))
    return "%s · %s" % (package_name, fallback)

def _has_value(value):
    return value not in (None, "", []) and value != {}


def _control(field, name):
    kind = (field or {}).get("kind") or "text"
    if kind == "choice":
        return "select"
    if kind == "number":
        return "number"
    if name in LONG_TEXT:
        return "textarea"
    return "text"


def _options(field):
    return [x.get("label") if isinstance(x, dict) else x
            for x in ((field or {}).get("options") or [])]


def _field_block(section, name, value, definition, meta):
    col = FIELD_TO_COLUMN.get(name)
    locked = bool((meta or {}).get("locked"))
    editable = bool(col and name not in UPSTREAM and not locked)
    path = f"{section}.{_camel(col or name)}"
    return {
        "kind": "field" if col else "text",
        "label": _label(definition, name),
        "field": name if col else None,
        "field_path": path,
        "class_name": path.replace(".", "-"),
        "value": value,
        "editable": editable,
        "locked": locked,
        "required": bool((definition or {}).get("required") or name in REQUIRED),
        "maxlen": 2000 if name in LONG_TEXT else None,
        "control": _control(definition, name),
        "options": _options(definition),
        "save_key": col,
        "lock_reason": ((meta or {}).get("locked_reason")
                        or ("由立项或前序环节带入，本环节不可修改" if name in UPSTREAM else "")),
        "hint": (meta or {}).get("hint") or "",
    }


# ── 标的表的列规范：界面、保存、成稿共用这一份 ───────────────────────────
# 每列 (存储键, 表头, 控件)。存储键同时写中英文两套是历史包袱：items_json 用
# 英文键，packages_json[i]["标的"] 用中文键，成稿层两边都认（demand_doc.py）。
# 前端按 key 读写，**不要再按列下标**——原来那套下标和表头差一格，填进去的值
# 会整体串位。
ITEM_COLUMNS = (
    # key,            中文键,        表头,                 控件
    ("catalog",       "品目",        "采购品目",            "text"),
    ("name",          "标的名称",     "标的名称",            "text"),
    ("qty",           "数量",        "数量",               "number"),
    ("unit",          "计量单位",     "单位",               "text"),
    ("unit_price",    "单价",        "单价（元）",           "number"),
    ("amount",        "标的金额",     "合计金额（元）",        "computed"),
    ("energy",        "节能",        "是否采购节能产品",       "yesno"),
    ("energy_reason", "未采购节能产品原因", "未采购节能产品原因", "text"),
    ("eco",           "环保",        "是否采购环保产品",       "yesno"),
    ("eco_reason",    "未采购环保产品原因", "未采购环保产品原因", "text"),
    ("import_ok",     "允许进口",     "是否采购进口产品",       "yesno"),
    ("industry",      "所属行业",     "标的物所属行业",        "text"),
)

ITEM_COLUMN_SPEC = [{"key": k, "cn": cn, "label": label, "control": ctrl}
                    for k, cn, label, ctrl in ITEM_COLUMNS]

ITEM_HEADER = ["序号"] + [label for _k, _cn, label, _c in ITEM_COLUMNS]


def _item_cell(item, key, cn):
    """一条标的里取某一列。英文键（items_json）和中文键（packages_json）都认。"""
    if not isinstance(item, dict):
        return ""
    value = item.get(key)
    if value in (None, ""):
        value = item.get(cn)
    return "" if value is None else value


def item_rows(value):
    """标的清单 → 界面表格的行。第一列是序号，其余按 ITEM_COLUMNS 顺序。"""
    rows = []
    for i, item in enumerate(value or [], 1):
        rows.append([i] + [_item_cell(item, k, cn) for k, cn, _l, _c in ITEM_COLUMNS])
    return rows


def _table_rows(name, value):
    if name == "标的":
        return list(ITEM_HEADER), item_rows(value)
    return [], []


def _normalise_packages(demand):
    try:
        packages = json.loads(getattr(demand, "packages_json", "") or "[]")
    except Exception:  # noqa: BLE001
        packages = []
    return packages if isinstance(packages, list) and packages else [{}]


def _package_table(package, name):
    value = package.get(name)
    if name == "标的":
        # 表里 4.x.8 标的具体情况：这个包下面有哪些标的。
        # 列和顶层那张完全一致，否则同一条标的在两处显示不一样。
        return list(ITEM_HEADER), item_rows(value), (value or [])
    if name in ("技术要求", "商务要求", "特殊资格要求"):
        rows = [[i, line] for i, line in enumerate(str(value or "").splitlines(), 1) if line.strip()]
        return ["序号", "内容"], rows, str(value or "")
    if name == "一般资格要求":
        source = value if isinstance(value, list) and value else demand_doc.GENERAL_QUALIFICATIONS
        rows = []
        for i, item in enumerate(source, 1):
            if isinstance(item, dict):
                rows.append([i, item.get("名称", ""), item.get("详细说明", "")])
            else:
                rows.append([i, str(item), demand_doc.QUALIFICATION_DETAIL])
        return ["序号", "资格要求名称", "资格要求详细说明"], rows, source
    factors = value if isinstance(value, dict) else {}
    order = ("价格分", "技术要求", "履约能力", "售后服务", "服务要求", "价格扣除")
    rows = [[name0, (factors.get(name0) or {}).get("分值", ""),
             (factors.get(name0) or {}).get("客观项", ""),
             (factors.get(name0) or {}).get("标准", "")] for name0 in order]
    return ["评审项", "分值", "客观评审项", "评审标准"], rows, factors


def build(demand, project=None):
    definitions = demand_doc.load_fields()
    by_name = {item.get("name"): item for item in definitions}
    # 同一项在清单里和节定义里叫法不同（3.6 清单写「项目级中小企业政策」、
    # 这边写「中小企业政策」），查不到定义 label 就丢编号，补几个别名。
    for alias, real in (("中小企业政策", "项目级中小企业政策"),
                        ("有无关联服务供应商", "有无关联服务供应商"),
                        ("是否科研设备采购", "是否省属高校、科研院所科研设备采购")):
        if alias not in by_name and real in by_name:
            by_name[alias] = by_name[real]
    raw = demand_doc.build_context_for(demand, project)
    effective, meta = field_dict.resolve(definitions, raw)
    missing = {item.get("name") for item in demand_doc.missing_fields(effective, meta)}
    sections = []

    for key, title, names in SECTIONS:
        blocks = []
        for name in names:
            if name != "需求调查是否需要" and not (meta.get(name) or {}).get("visible", True):
                continue
            if name == "标的":
                header, rows = _table_rows(name, effective.get(name))
                path = "implementation.items"
                blocks.append({
                    "kind": "table", "label": "采购标的", "field": name,
                    "field_path": path, "class_name": path.replace(".", "-"),
                    "value": effective.get(name) or [], "header": header, "rows": rows,
                    "columns": ITEM_COLUMN_SPEC,
                    "editable": True, "required": True, "control": "table",
                    "locked": False,
                    "save_key": "items", "lock_reason": "",
                })
            else:
                blocks.append(_field_block(key, name, effective.get(name), by_name.get(name), meta.get(name)))
        sections.append({"key": key, "title": title, "incomplete": any(
            b.get("field") in missing for b in blocks), "blocks": blocks})

    packages = _normalise_packages(demand)
    package_blocks = []
    for index, package in enumerate(packages):
        package_name = f"合同包{demand_doc._cn(index + 1)}"
        package_blocks.append({
            "kind": "text", "label": "采购包", "value": package_name,
            "field": None, "field_path": "subcontract.packageName",
            "class_name": "subcontract-packageName", "editable": False,
            "locked": False,
            "required": False, "lock_reason": "由采购包划分结果生成",
        })
        for name, label, control, required in PACKAGE_SIMPLE:
            definition = by_name.get(name) or {}
            value = package.get(name)
            if value in (None, ""):
                value = effective.get(name)
            path = f"subcontract.{PACKAGE_PATH[name]}"
            package_blocks.append({
                # 表上印的是「4.1.1预算金额（元）」，界面就照着显示，
                # 不然填的人对不上号（黄新博：得按照原文写）。
                "kind": "field",
                "label": _pkg_label(definition, label, index, package_name, name),
                "field": name,
                "field_path": path, "class_name": path.replace(".", "-"), "value": value,
                "editable": True, "required": required, "control": control,
                "locked": False,
                "options": _options(definition), "save_key": "packages_json",
                "package_index": index, "package_field": name, "lock_reason": "", "maxlen": None,
            })
        for name, label in (("标的", "标的具体情况"),
                            ("技术要求", "技术要求"), ("商务要求", "商务要求"),
                            ("一般资格要求", "一般资格要求"), ("特殊资格要求", "特殊资格要求"),
                            ("评审因素", "评审因素")):
            header, rows, value = _package_table(package, name)
            path = f"subcontract.{PACKAGE_PATH[name]}"
            package_blocks.append({
                "kind": "table",
                "label": _pkg_label(by_name.get(name), label, index, package_name, name),
                "field": name,
                "field_path": path, "class_name": path.replace(".", "-"), "value": value,
                "header": header, "rows": rows,
                "columns": ITEM_COLUMN_SPEC if name == "标的" else None,
                "editable": True, "required": True,
                "locked": False,
                "control": "table", "save_key": "packages_json", "package_index": index,
                "package_field": name, "lock_reason": "",
            })
    target = next(x for x in sections if x["key"] == "subcontract")
    target["blocks"] = package_blocks + target["blocks"]
    target["incomplete"] = target["incomplete"] or any(
        b.get("required") and not _has_value(b.get("value")) for b in package_blocks)

    return {"sections": sections, "packages": packages,
            "field_path_format": "section.field (循环字段按出现顺序区分)"}
