# -*- coding: utf-8 -*-
"""字段字典：条件、联动、写死值都放在这儿，Word 模板保持「笨」。

为什么这么分（黄新博 2026-08-19 认可的方向）：
  · Word 模板只写占位符和条款原文——**只说要什么，不说什么时候要**，文员维护得了；
  · 什么条件下出现、锁成什么值、选了这项自动带出什么——配在字典里，
    采购部配一次、所有文书通用。
这是 procurement-doc-templates（pdt）那条底线「模板的第一使用者是文员，
不是工程师」在系统侧的落法：不引入 {% if %}，逻辑不进 Word。

字典能表达四件事：
  show_when   满足条件才出现（不满足就不显示、也不参与出稿）
  lock_when   满足条件就锁成某个值，人改不了、AI 也不参与
  hint_when   满足条件时给一句提示（只提示，不强制）
  options[].sets  选中某个选项，自动带出一组写死的值
"""
import io
import json
import os
import re

DICT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "templates_docx")


def _norm(v):
    return re.sub(r"[\s　]+", "", str(v if v is not None else ""))


def load(name="2.2采购需求表"):
    """读字段字典。找不到就返回空表，不让出稿因为字典缺失整个挂掉。"""
    path = os.path.join(DICT_DIR, f"{name}.fields.json")
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:                                    # noqa: BLE001
            return []


def _cond_ok(cond, values):
    """条件形如 {"项目所属分类": "货物"}，多个键之间是「且」。

    值支持写成列表表示「取其一即可」：{"项目所属分类": ["货物", "工程"]}。
    """
    if not cond:
        return True
    for key, want in cond.items():
        got = _norm(values.get(key))
        if isinstance(want, (list, tuple, set)):
            if got not in {_norm(w) for w in want}:
                return False
        elif got != _norm(want):
            return False
    return True


def _option_label(opt):
    return opt.get("label") if isinstance(opt, dict) else str(opt)


def option_labels(field):
    """给模板/界面用的纯选项名列表。"""
    return [_option_label(o) for o in (field.get("options") or [])]


def resolve(fields, values):
    """按字典把人填的值算成「实际生效的值」。

    返回 (effective, meta)：
      effective  出稿真正用的值——锁定的以字典为准，隐藏的清空
      meta       每个字段的 {visible, locked, locked_reason, hint}，界面照它渲染

    先算 sets（选项带出的值），再算 lock（锁定优先级最高），最后算 show。
    锁定和隐藏都可能依赖别的字段，所以整体多跑几轮直到不再变化——
    字段之间是链式依赖的（选了 A → 带出 B → B 决定 C 显不显示）。
    """
    by_name = {f["name"]: f for f in fields if f.get("name")}
    eff = dict(values or {})
    meta = {}

    for _ in range(5):          # 链式依赖跑几轮就收敛了，防死循环
        changed = False

        # ① 选项携带的固定值
        for name, f in by_name.items():
            for opt in (f.get("options") or []):
                if not isinstance(opt, dict) or not opt.get("sets"):
                    continue
                if _norm(eff.get(name)) != _norm(opt.get("label")):
                    continue
                for k, v in opt["sets"].items():
                    if _norm(eff.get(k)) != _norm(v):
                        eff[k] = v
                        changed = True

        # ② 条件锁定
        for name, f in by_name.items():
            for rule in (f.get("lock_when") or []):
                if _cond_ok(rule.get("if"), eff):
                    if _norm(eff.get(name)) != _norm(rule.get("value")):
                        eff[name] = rule.get("value")
                        changed = True

        if not changed:
            break

    # ③ 显示与提示（要在值都定下来之后算）
    for name, f in by_name.items():
        visible = _cond_ok(f.get("show_when"), eff)
        locked, reason = False, ""
        for rule in (f.get("lock_when") or []):
            if _cond_ok(rule.get("if"), eff):
                locked = True
                reason = rule.get("reason") or _lock_reason(rule)
                break
        # 被别的选项带出来的值同样锁住——那是写死的法条依据，不许改
        for owner, of in by_name.items():
            for opt in (of.get("options") or []):
                if (isinstance(opt, dict) and opt.get("sets") and name in opt["sets"]
                        and _norm(eff.get(owner)) == _norm(opt.get("label"))):
                    locked = True
                    reason = reason or f"由「{of.get('label') or owner}」的选项决定，不可修改"
        hint = ""
        for rule in (f.get("hint_when") or []):
            if _cond_ok(rule.get("if"), eff):
                hint = rule.get("hint") or ""
                break
        meta[name] = {"visible": visible, "locked": locked,
                      "locked_reason": reason, "hint": hint or f.get("hint", "")}
        if not visible:
            eff.pop(name, None)          # 不显示的字段不进成稿，免得留下上一轮的残值

    return eff, meta


def _lock_reason(rule):
    cond = rule.get("if") or {}
    part = "、".join(f"{k}＝{v}" for k, v in cond.items())
    return f"{part} 时固定为「{rule.get('value')}」" if part else "固定值，不可修改"


def validate(fields, values):
    """出稿前的校验。返回 [错误说明]，空表示可以出稿。"""
    eff, meta = resolve(fields, values)
    errs = []
    for f in fields:
        name = f.get("name")
        if not name or not meta.get(name, {}).get("visible", True):
            continue
        v = eff.get(name)
        if f.get("required") and (v is None or _norm(v) == ""):
            errs.append(f"「{f.get('label') or name}」必填")
        if f.get("kind") == "number" and _norm(v):
            try:
                n = float(v)
            except (TypeError, ValueError):
                errs.append(f"「{f.get('label') or name}」要填数字，现在是「{v}」")
                continue
            if f.get("min") is not None and n < f["min"]:
                errs.append(f"「{f.get('label') or name}」不能小于 {f['min']}")
            if f.get("max") is not None and n > f["max"]:
                errs.append(f"「{f.get('label') or name}」不能大于 {f['max']}")
            dec = f.get("decimals")
            if dec is not None and "." in str(v) and len(str(v).split(".")[1]) > dec:
                errs.append(f"「{f.get('label') or name}」最多 {dec} 位小数")
        if f.get("kind") == "choice" and _norm(v):
            labels = {_norm(x) for x in option_labels(f)}
            if labels and _norm(v) not in labels:
                errs.append(f"「{f.get('label') or name}」的值「{v}」不在选项里")
    return errs
