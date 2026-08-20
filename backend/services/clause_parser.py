# -*- coding: utf-8 -*-
"""技术参数拆条款：把一大段参数文字拆成结构化的条款清单。

黄新博 2026-08-20 的诊断：现在的 Agent 把 2000 字原样搬进一个文本框，
而他手工做出来的是一张四列表（参数性质/序号/名称/内容），★▲ 提取成独立列。
差的这一步就是「编排」。

分工（这条是关键）：
  · **拆条款、认编号层级、认 ★▲ —— 代码干**。确定性的事，模型会数错，人也没法验。
  · **判断「哪些条款是清单明细不该计数」—— 模型干**。要读懂语义，正则做不到
    （「★15 配置清单」下面 12 条是电源、主机、模块，不是 12 个技术条款）。
  · **最终计数 —— 代码干**。按模型的判断结果数，可复算。

计数规则来自模板原文：
  「（1）无子项的条款：以每项条款为 1 项计算；（2）有子项的条款：以最末级的子项为 1 项计算」
实测：肺功能仪那份按此规则数出 ▲ 13 条，与手工成稿完全一致。
"""
import re

STAR = "★"
TRI = "▲"

# 编号：1、 / 1. / 1.2 / 1.2.3 ，允许前面带 ★▲ 和空白
NUM_RE = re.compile(r"^\s*([★▲☆△]?)\s*(\d+(?:[.．]\d+)*)\s*[、.．)）]?\s*(.*)$")
# 设备名/分组标题：整行没有编号，且不长（多设备项目里每台设备一个标题）
GROUP_MAX = 30


def _norm_mark(ch):
    if ch in ("★", "☆"):
        return STAR
    if ch in ("▲", "△"):
        return TRI
    return ""


def parse(text):
    """把技术参数文字拆成条款清单。

    返回 [{group, no, level, mark, text, is_leaf}]，顺序即原文顺序。
    group 是所属设备/分组名（单设备项目为空）。
    """
    rows = []
    group = ""
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        m = NUM_RE.match(line)
        if not m:
            # 没编号的短行当分组标题（多设备项目里的设备名）
            if len(line) <= GROUP_MAX and not line.endswith("："):
                group = line
            elif len(line) <= GROUP_MAX:
                group = line.rstrip("：:")
            else:
                # 长的无编号行：接到上一条后面，别丢
                if rows:
                    rows[-1]["text"] += " " + line
            continue
        mark, no, body = _norm_mark(m.group(1)), m.group(2).replace("．", "."), m.group(3)
        rows.append({
            "group": group,
            "no": no,
            "parts": tuple(int(x) for x in no.split(".")),
            "level": no.count(".") + 1,
            "mark": mark,
            "text": (body or "").strip(),
            "raw": line,
        })

    # 标末级：同一分组内，没有更深一层编号以它为前缀的，就是末级
    by_group = {}
    for r in rows:
        by_group.setdefault(r["group"], []).append(r)
    for g, items in by_group.items():
        nums = [x["parts"] for x in items]
        for r in items:
            n = r["parts"]
            r["is_leaf"] = not any(o[:len(n)] == n and len(o) > len(n) for o in nums)
    return rows


def count(rows, whole_tops=()):
    """按模板规则计数。

    whole_tops: 需要「整条算 1 项、不拆子项」的顶层编号集合，形如 {("配置清单组", "15")}
                或简单的 {"15"}（单设备时）。这来自模型的判断——
                「★15 配置清单」下面是货物明细，拆开数就从 17 变成 28，全错。
    返回 {"general": n, "star": n, "tri": n, "items": [...]}
    """
    wt = set()
    for x in whole_tops:
        wt.add(x if isinstance(x, tuple) else (None, str(x)))

    def is_whole(r):
        return ((r["group"], r["no"].split(".")[0]) in wt
                or (None, r["no"].split(".")[0]) in wt)

    counted = []
    for r in rows:
        if is_whole(r):
            if r["level"] == 1:          # 整条只算它自己，子项不拆
                item = dict(r)
                # 「★15 配置清单」这种：★ 表示整条是实质性要求，但计数时它就是
                # **一个普通计数项**——手工成稿把它算进了「一般 17 条」里。
                # 不这么算就只有 16 条，差的正是它。
                item["count_as"] = "general"
                counted.append(item)
            continue
        if not r.get("is_leaf"):
            continue
        item = dict(r)
        item["count_as"] = ("star" if r["mark"] == STAR
                            else "tri" if r["mark"] == TRI else "general")
        counted.append(item)

    star = [r for r in counted if r["count_as"] == "star"]
    tri = [r for r in counted if r["count_as"] == "tri"]
    general = [r for r in counted if r["count_as"] == "general"]
    return {
        "general": len(general), "star": len(star), "tri": len(tri),
        "total": len(counted),
        "items": counted,
        "general_items": general, "star_items": star, "tri_items": tri,
    }


def to_table(rows):
    """整理成成稿要的表：参数性质 / 序号 / 技术要求名称 / 技术要求内容。

    黄新博手工做的就是这四列，★▲ 从句子里提到独立一列。
    """
    out = []
    for r in rows:
        out.append({
            "参数性质": r["mark"],
            "分组": r["group"],
            "序号": r["no"],
            "内容": r["text"],
        })
    return out


def split_scores(general_n, tri_n, total_score=50.0, tri_ratio=None):
    """把技术分在「一般条款」和「▲ 条款」之间分配。

    肺功能仪那份手工成稿：一般 17 条 ×10.5 分、▲ 13 条 ×39.5 分，合计 50。
    ▲ 占 79%——这是人定的权重，不是算出来的，所以 tri_ratio 要能传进来。
    默认按条数加权：▲ 一条顶一般三条（经验值，界面上可改）。
    """
    if general_n <= 0 and tri_n <= 0:
        return {"general_score": 0.0, "tri_score": 0.0}
    if tri_ratio is None:
        w = 3.0
        denom = general_n + w * tri_n
        tri_score = total_score * (w * tri_n) / denom if denom else 0.0
    else:
        tri_score = total_score * float(tri_ratio)
    tri_score = round(tri_score, 2)
    return {"general_score": round(total_score - tri_score, 2),
            "tri_score": tri_score}
