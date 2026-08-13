"""投标文件 AI 审查服务：六类条目抽取 + 分阶段证据定位/判定/评分。

两个后台工作流（threading，状态写 DB，前端轮询）：
  ① process_proc_doc(task_id)：采购文件 OCR → 5 次 LLM 抽取
     （A 概要+评审方式 → B 资格 → C 实质性 → D 商务 → E 打分项）→ criteria 表
  ② review_bid_file(result_id)：投标文件 OCR → 按「通用+所投包」筛选条目 →
     分批扫描（判定类出 verdict，打分项出建议分）→ 抽总报价 → result_items

LLM 走全局配置（llm_client，后台可切 DeepSeek），usage_ctx.feature='bid-review'。
AI 仅辅助定位与初判，最终判定/得分以经办人复核为准。
"""
import datetime
import json
import math
import os
import re
import threading

import requests

from models import db
from models.bid_review import (
    BidReviewTask, BidReviewCriteria, BidReviewResult, BidReviewResultItem,
    BidReviewResultFile, LOT_COMMON,
)
from services.llm_client import chat_json, embed

# OCR 服务（与 routes/ocr_api.py 一致，可被 PMS_OCR_URL 覆盖）
OCR_URL = os.environ.get("PMS_OCR_URL", "http://192.168.1.12:8118")
OCR_TIMEOUT = 1800      # 秒（30分钟）；超大扫描件单文件可能 200+ 页，留足时间不被丢
# 容器化审核服务（绞杀者：审核算法收敛到 9010 单一真源；不可用则本地兜底）
BID_REVIEW_SVC = os.environ.get("PMS_BID_REVIEW_URL", "http://127.0.0.1:9010")

PAGES_PER_BATCH = 20    # 投标文件分批扫描：每批页数
# 单次抽取调用送入 LLM 的采购文件文本预算（关键词选页后拼接）
EXTRACT_MAX_CHARS = int(os.environ.get("PMS_BR_EXTRACT_CHARS", "80000"))
CRIT_TEXT_LIMIT = 12000  # 扫描时条件清单文本超此长度则按类别拆两组分别跑批
# 投标审查闭环：初扫后对「未找到」条目最多再聚焦复检几轮（含初扫；2=最多两轮，1=关闭复检）
BR_MAX_ROUNDS = int(os.environ.get("PMS_BR_MAX_ROUNDS", "2"))


def _now():
    return datetime.datetime.now().isoformat(timespec="seconds")


# ── 文档转文本（分情况：文本 PDF / Word 直读，扫描件走 OCR）──────────
# 平均每页字符数低于此值视为扫描件/图片型 PDF，转走 OCR
PDF_TEXT_MIN_CHARS_PER_PAGE = 60
DOCX_CHARS_PER_PAGE = 1800   # docx 无固定分页，按字数切伪页供定位/分批
# 图文混合页判定：文字少且图片占比高 → 该页正文是扫描图，文本提取读不到
HYBRID_PAGE_TEXT_MAX = 150   # 页文字少于此（多为页眉页脚水印）
HYBRID_PAGE_IMG_RATIO = 0.4  # 且图片覆盖超过此比例 → 判为图片页


def _page_image_ratio(page):
    """页面被图片覆盖的面积占比（用于识别扫描图嵌在 PDF 里的页）。"""
    pa = page.rect.width * page.rect.height
    if pa <= 0:
        return 0.0
    area = 0.0
    for blk in page.get_text("dict").get("blocks", []):
        if blk.get("type") == 1:          # 1 = 图片块
            b = blk["bbox"]
            area += (b[2] - b[0]) * (b[3] - b[1])
    return area / pa


def _pdf_text_md(path):
    """文本型 PDF 直接抽文字，返回带真实 <!--page:N--> 标记的文本；
    扫描件或图文混合件（证照/检测报告以图片嵌入）返回 None，由调用方整体走 OCR。

    旧版只看平均字数——封面有字、正文是扫描图的混合件会被误判为文本件、漏掉图片正文
    （如财务证明、医疗器械证照、检测报告）。现增加逐页图片占比判定。"""
    import fitz
    doc = fitz.open(path)
    parts, total, img_pages = [], 0, 0
    for i, page in enumerate(doc, 1):
        txt = page.get_text("text").strip()
        total += len(txt)
        if len(txt) < HYBRID_PAGE_TEXT_MAX and _page_image_ratio(page) > HYBRID_PAGE_IMG_RATIO:
            img_pages += 1
        parts.append(f"<!--page:{i}-->\n{txt}")
    n = doc.page_count
    doc.close()
    if not n:
        return None
    # 整份文字过少 → 扫描件，整体 OCR
    if total / n < PDF_TEXT_MIN_CHARS_PER_PAGE:
        return None
    # 图文混合：存在实质性图片页（正文是扫描图）→ 整体 OCR 以免漏图
    if img_pages >= 2 or (n <= 5 and img_pages >= 1):
        return None
    return "\n\n".join(parts)


def _docx_to_md(path):
    """Word(.docx) 按文档顺序抽段落与表格（表格行转「a | b | c」）。
    docx 无固定分页，按 DOCX_CHARS_PER_PAGE 切伪页——页码仅供证据定位参考，
    与 Word 里的真实页码不一定一致。"""
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    lines = []
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            t = Paragraph(child, doc).text.strip()
            if t:
                lines.append(t)
        elif child.tag == qn("w:tbl"):
            for row in Table(child, doc).rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                if any(cells):
                    lines.append(" | ".join(cells))
    if not lines:
        raise RuntimeError("Word 文档未读到内容，请检查文件是否有效")

    pages, buf, used, page_no = [], [], 0, 1
    for line in lines:
        buf.append(line)
        used += len(line)
        if used >= DOCX_CHARS_PER_PAGE:
            pages.append(f"<!--page:{page_no}-->\n" + "\n".join(buf))
            buf, used, page_no = [], 0, page_no + 1
    if buf:
        pages.append(f"<!--page:{page_no}-->\n" + "\n".join(buf))
    return "\n\n".join(pages)


def _doc_to_md(path, filename=None):
    """文档 → 带页标记的文本。分情况：
    .docx 直读；文本型 PDF 直接抽字；扫描 PDF/图片走 OCR 服务。"""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".docx":
        return _docx_to_md(path)
    if ext == ".pdf":
        try:
            md = _pdf_text_md(path)
        except Exception:
            md = None     # PDF 损坏/加密等，交给 OCR 兜底
        if md:
            return md
    return _ocr_file(path, filename)


# ── OCR ────────────────────────────────────────────────────────────────
# 超过此页数的 PDF 切块逐块 OCR：每块独立请求，避免单请求超时 + 显存逐页累积 OOM。
# 切块让 OCR 对任意大小文件鲁棒（显存占用恒定为一块的量），不依赖显存大小。
OCR_CHUNK_PAGES = 15


def _ocr_post(path):
    """向 OCR 服务发一份文件（一块或整份），返回 markdown 文本。"""
    with open(path, "rb") as fp:
        resp = requests.post(
            f"{OCR_URL}/ocr",
            files={"file": (os.path.basename(path), fp, "application/octet-stream")},
            timeout=OCR_TIMEOUT,
        )
    resp.raise_for_status()
    return resp.json().get("markdown", "")


def _ocr_file(path, filename=None):
    """调 OCR 服务识别 PDF/图片，返回含 <!--page:N--> 页标记的 markdown。

    大 PDF 按 OCR_CHUNK_PAGES 页切块逐块 OCR（避免超时/显存累积 OOM），全局重编页码；
    小 PDF/图片整份发。上送文件名必须带合法扩展名（统一用存储文件名 uuid.pdf）。
    """
    n = 0
    if os.path.splitext(path)[1].lower() == ".pdf":
        try:
            import fitz
            _d = fitz.open(path)
            n = _d.page_count
            _d.close()
        except Exception:
            n = 0

    if n > OCR_CHUNK_PAGES:
        import fitz
        import tempfile
        doc = fitz.open(path)
        parts, gp = [], 0
        for start in range(0, n, OCR_CHUNK_PAGES):
            end = min(start + OCR_CHUNK_PAGES, n) - 1
            sub = fitz.open()
            sub.insert_pdf(doc, from_page=start, to_page=end)
            tf = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            sub.save(tf.name); sub.close(); tf.close()
            try:
                chunk_md = _ocr_post(tf.name)
            finally:
                try:
                    os.unlink(tf.name)
                except Exception:
                    pass
            # 块内页码从 1 起，重编为全局连续页码
            for _, txt in split_pages(chunk_md):
                gp += 1
                parts.append(f"<!--page:{gp}-->\n{txt}")
        doc.close()
        md = "\n\n".join(parts)
    else:
        md = _ocr_post(path)

    if not md.strip():
        raise RuntimeError("OCR 未识别出内容，请检查文件是否有效")
    return md


def split_pages(md):
    """按 <!--page:N--> 切分 markdown，返回 [(page_no, text), ...]（按页码升序）。"""
    parts = re.split(r"<!--page:(\d+)-->", md)
    pages = []
    # split 结果形如 ['', '1', text1, '2', text2, ...]
    for i in range(1, len(parts) - 1, 2):
        pages.append((int(parts[i]), parts[i + 1].strip()))
    if not pages:           # 无页标记（旧版 OCR / 单页）：整体当第 1 页
        pages = [(1, md.strip())]
    return pages


def _semantic_order(pages, query):
    """按与 query 的语义相似度对页索引降序排列；嵌入未配置/失败时返回 []。

    单篇文档、几百页量级，内存里算余弦即可，无需向量库。"""
    if not query or len(pages) < 2:
        return []
    vecs = embed([t[:3000] for _, t in pages] + [query])  # 每页截断，控量
    if not vecs or len(vecs) != len(pages) + 1:
        return []
    qv = vecs[-1]
    nq = math.sqrt(sum(x * x for x in qv)) or 1.0

    def sim(v):
        nv = math.sqrt(sum(x * x for x in v))
        return sum(a * b for a, b in zip(v, qv)) / (nv * nq) if nv else 0.0

    return sorted(range(len(pages)), key=lambda i: sim(vecs[i]), reverse=True)


def _select_pages(pages, keywords, budget=None, neighbor=1, query=None):
    """混合选页：关键词命中页（含前后 neighbor 页）优先，其次语义相似页（若配了
    嵌入端点且给定 query），最后从文首顺序补页；全部按页码拼接（带 <!--page:N-->）。
    无命中且无嵌入时即退化为「从文首截取 budget 字符」（与原行为一致）。"""
    budget = budget or EXTRACT_MAX_CHARS
    if not pages:
        return ""
    hit = set()
    for i, (_, txt) in enumerate(pages):
        if any(k in txt for k in keywords):
            for j in range(max(0, i - neighbor), min(len(pages), i + neighbor + 1)):
                hit.add(j)

    # 语义召回：补关键词漏命中的页（同义/近义表述）。未配嵌入时为空，行为不变。
    sem_rank = [i for i in _semantic_order(pages, query) if i not in hit]

    picked, seen, used = [], set(), 0

    def _add(i):
        nonlocal used
        if i in seen:
            return True
        block = f"<!--page:{pages[i][0]}-->\n{pages[i][1]}"
        if used + len(block) > budget:
            block = block[:budget - used]
        seen.add(i)
        picked.append((i, block))
        used += len(block)
        return used < budget

    for i in sorted(hit):           # 1) 关键词命中页（含邻页）
        if not _add(i):
            break
    for i in sem_rank:              # 2) 语义相似页（相似度降序，补漏）
        if used >= budget:
            break
        _add(i)
    for i in range(len(pages)):     # 3) 文首顺序兜底
        if used >= budget:
            break
        _add(i)
    picked.sort(key=lambda t: t[0])
    return "\n\n".join(b for _, b in picked)


# ── ① 采购文件：OCR + 概要识别 + 四类条目抽取 ──────────────────────────
EXTRACT_SYSTEM = (
    "你是医院采购评审专家助手，负责从采购文件（招标/竞选/磋商文件）中抽取指定类别的条目。"
    "提取时保留原文表述，不要抽取与指定类别无关的内容。"
)

OVERVIEW_KEYWORDS = ["分包", "包号", "标段", "品目", "预算", "最高限价",
                     "采购需求一览", "评标办法", "评审方法", "综合评分", "最低评标价"]

OVERVIEW_USER_TMPL = (
    "以下是采购文件 OCR 文本节选，每页开头有 <!--page:N--> 页码标记。\n"
    "请识别项目概要与评审方式，输出 JSON：\n"
    '{{"eval_method": "综合评分法 或 最低评标价法（文件未明确则填空字符串）",\n'
    ' "price_score_max": "价格分满分数字（如 30）；最低评标价法或未明确填空字符串",\n'
    ' "price_formula": "价格分计算规则原文摘录（150字内）；无则填空字符串",\n'
    ' "lots": [{{"lot_no": "包号（如 01）", "name": "包名或内容简述", "budget": "该包预算/最高限价"}}],\n'
    ' "subjects": [{{"content": "标的信息条目（品目、数量、预算、最高限价等）", "source_page": 3}}],\n'
    ' "lot_summary": "分包情况一句话说明；不分包填\\"本项目不分包\\""}}\n'
    "不分包时 lots 填空数组 []；只输出 JSON，不要其他文字。\n\n"
    "【采购文件文本】\n{doc}"
)

# 类别 → (定义说明, 关键词)。实质性与商务天然有重叠，由 prompt 限定+人工编辑兜底。
CATEGORY_DEFS = {
    "资格": (
        "投标人资格条件：文件明确要求投标人/竞选人/供应商必须满足的资格性条件，"
        "包括营业执照/法人资格、财务/纳税/社保、行业资质许可证、业绩要求、人员配置、"
        "信用记录（无重大违法、不在失信名单）、授权/经营范围、保证金、其他强制性资格要求。"
        "不要抽取评分标准、技术参数细节、合同条款。",
        ["资格", "供应商须知", "投标人须知", "资质", "信用"],
    ),
    "实质性": (
        "实质性要求：不满足即导致投标无效/被否决的条款。重点抽取："
        "①技术/服务/采购需求章节中带★或▲标记的条款——逐条抽取，每个★条款单独一条，保留原文；"
        "②评标办法/符合性审查中列明的「不满足即无效投标」情形。"
        "不要抽取：资格条件、商务条款（交货/付款/质保/售后等）、普通评分项，"
        "以及投标人须知中关于报价、签章、密封、提交、解密等程序性规定。",
        ["实质性", "★", "▲", "符合性", "无效投标", "无效响应", "废标", "否决"],
    ),
    "商务": (
        "商务要求：交货期/工期、交货地点、质保期、付款方式、售后服务、培训、"
        "安装调试等商务条款（其中标注实质性的也要抽取，类别仍归商务）。"
        "不要抽取资格条件、技术参数、评分标准。",
        ["商务", "交货", "工期", "质保", "付款", "售后", "服务承诺", "培训", "合同"],
    ),
}

CATEGORY_USER_TMPL = (
    "以下是采购文件 OCR 文本节选，每页开头有 <!--page:N--> 页码标记。\n"
    "请抽取全部【{cat_name}】，类别定义：{cat_def}\n"
    "注意：资格/符合性审查多为三列表格——审查内容 | 具体标准和要求 | 关联（投标/响应）文件格式文件。"
    "必须把三部分都抽全，不能只抽第一列。输出 JSON：\n"
    '{{"criteria": [{{"seq": 1, "content": "审查内容/条目名称（第一列原文）", '
    '"standard": "具体标准和要求（第二列原文：是否需提供佐证材料、可接受的材料清单/数值标准）", '
    '"format_files": "关联格式文件（第三列原文，如：具有健全财务会计制度的证明材料.docx,投标（响应）函）", '
    '"lot_no": "通用", "source_page": 12}}, ...]}}\n'
    "若某条没有第二/三列（如纯文字条款），standard/format_files 填空字符串；\n"
    "lot_no：该条仅适用于某个包/标段时填该包号（须与文件分包一致），否则填\"通用\"；\n"
    "source_page 填条目所在页码（整数）；只输出 JSON，不要其他文字。\n\n"
    "【采购文件文本】\n{doc}"
)

SCORE_KEYWORDS = ["评分标准", "评标办法", "评分细则", "分值", "综合评分"]

SCORE_USER_TMPL = (
    "以下是采购文件 OCR 文本节选，每页开头有 <!--page:N--> 页码标记。\n"
    "请抽取评分标准中的全部打分项（技术分、商务分等），"
    "不要抽取价格分（价格分由系统按公式计算）。输出 JSON：\n"
    '{{"criteria": [{{"seq": 1, "content": "评分项名称/内容", "max_score": 10, '
    '"score_rule": "评分细则原文（如何给分扣分）", "lot_no": "通用", "source_page": 45}}, ...]}}\n'
    "max_score 填该项满分（数字）；lot_no 规则同前（仅适用某包填包号，否则\"通用\"）；"
    "只输出 JSON，不要其他文字。\n\n"
    "【采购文件文本】\n{doc}"
)


def _extract_all(task, usage_ctx):
    """5 次 LLM 调用抽取概要与四类条目并写表。返回 (条目数, 警告列表)。

    单类抽取失败不致命（记警告，其余照写）；全部失败才抛错。
    """
    pages = split_pages(task.proc_doc_ocr_md)
    warnings = []
    lots = []

    def _prog(n):
        task.progress = f"抽取中 {n}/5"
        db.session.commit()

    def _call(user_text):
        return chat_json(EXTRACT_SYSTEM, user_text, temperature=0.1,
                         max_tokens=8192, timeout=300, usage_ctx=usage_ctx)

    def _call_items(user_text):
        """条目类调用；模型偶发返回空列表，空结果重试一次再认。"""
        items = []
        for _ in range(2):
            out = _call(user_text)
            items = out if isinstance(out, list) else (out.get("criteria") or [])
            if items:
                break
        return items

    # A：概要+评审方式
    _prog(1)
    try:
        out = _call(OVERVIEW_USER_TMPL.format(
            doc=_select_pages(pages, OVERVIEW_KEYWORDS,
                              query="项目概要、分包/标段情况、评审方式（综合评分法或最低评标价法）、价格分计算规则")))
        if not isinstance(out, dict):
            raise RuntimeError("概要返回格式异常")
        method = (out.get("eval_method") or "").strip()
        task.eval_method = method if method in ("综合评分法", "最低评标价法") else ""
        task.price_score_max = str(out.get("price_score_max") or "").strip()[:20]
        task.price_formula = (out.get("price_formula") or "").strip()[:500]
        for l in out.get("lots") or []:
            if isinstance(l, dict) and str(l.get("lot_no") or "").strip():
                lots.append({
                    "lot_no": str(l.get("lot_no")).strip()[:30],
                    "name": str(l.get("name") or "").strip()[:200],
                    "budget": str(l.get("budget") or "").strip()[:100],
                })
        task.lots_json = json.dumps(lots, ensure_ascii=False)
        # 分包明细在 lots_json（前端以表格展示），summary 只放说明与标的
        summary = []
        if (out.get("lot_summary") or "").strip():
            summary.append({"kind": "分包", "content": out["lot_summary"].strip(),
                            "source_page": None})
        for s in out.get("subjects") or []:
            if isinstance(s, dict) and (s.get("content") or "").strip():
                p = s.get("source_page")
                summary.append({
                    "kind": "标的", "content": s["content"].strip(),
                    "source_page": int(p) if isinstance(p, (int, float)) else None,
                })
        task.summary_json = json.dumps(summary, ensure_ascii=False)
        db.session.commit()
    except Exception as e:
        warnings.append(f"概要/评审方式识别失败（可手工选择）：{e}")

    valid_lots = {l["lot_no"] for l in lots}

    def _norm_lot(it):
        lot = str(it.get("lot_no") or "").strip()
        return lot if lot in valid_lots else LOT_COMMON

    # B/C/D/E：四类条目
    rows = []
    step = 1
    for cat, (cat_def, keywords) in CATEGORY_DEFS.items():
        step += 1
        _prog(step)
        try:
            items = _call_items(CATEGORY_USER_TMPL.format(
                cat_name=f"{cat}要求", cat_def=cat_def,
                doc=_select_pages(pages, keywords, query=cat_def)))
            for it in items:
                content = (it.get("content") or "").strip()
                if not content:
                    continue
                # 把三列结构合进 content：审查内容 ｜标准 ｜应提交材料，
                # 供承诺制判定（标准→是否要佐证）与证据定位（应提交→找哪份文件）
                std = (it.get("standard") or "").strip()
                fmt = (it.get("format_files") or "").strip()
                full = content
                if std:
                    full += f"\n【具体标准和要求】{std}"
                if fmt:
                    full += f"\n【应提交格式文件】{fmt}"
                p = it.get("source_page")
                rows.append({
                    "category": cat, "content": full, "lot_no": _norm_lot(it),
                    "max_score": None, "score_rule": "",
                    "source_page": int(p) if isinstance(p, (int, float)) else None,
                })
        except Exception as e:
            warnings.append(f"{cat}要求抽取失败（可手工补录）：{e}")

    # E：打分项（最低评标价法无打分环节；评审方式未识别时照抽，便于人工确认）
    step += 1
    _prog(step)
    if task.eval_method != "最低评标价法":
        try:
            items = _call_items(SCORE_USER_TMPL.format(
                doc=_select_pages(pages, SCORE_KEYWORDS,
                                  query="评分标准、评标办法、评分细则、各打分项及其分值（技术分、商务分）")))
            for it in items:
                content = (it.get("content") or "").strip()
                if not content:
                    continue
                try:
                    ms = float(it.get("max_score"))
                except (TypeError, ValueError):
                    ms = None
                p = it.get("source_page")
                rows.append({
                    "category": "打分", "content": content, "lot_no": _norm_lot(it),
                    "max_score": ms, "score_rule": (it.get("score_rule") or "").strip(),
                    "source_page": int(p) if isinstance(p, (int, float)) else None,
                })
        except Exception as e:
            warnings.append(f"打分项抽取失败（可手工补录）：{e}")

    if not rows:
        raise RuntimeError("；".join(warnings) or "未能从采购文件中抽取到条目，"
                           "请检查文件内容或手工录入")

    # 重抽时清掉旧条目；按 资格→实质性→商务→打分 全局连续编 seq
    db.session.execute(db.delete(BidReviewCriteria).where(
        BidReviewCriteria.task_id == task.id))
    now = _now()
    for i, r in enumerate(rows, 1):
        db.session.add(BidReviewCriteria(
            task_id=task.id, seq=i, category=r["category"], lot_no=r["lot_no"],
            content=r["content"], max_score=r["max_score"],
            score_rule=r["score_rule"], source_page=r["source_page"],
            created_at=now,
        ))
    return len(rows), warnings


def process_proc_doc(app, task_id, usage_ctx):
    """后台线程：采购文件 OCR → 抽取。状态：ocr_proc_doc → extracting → criteria_ready。"""
    with app.app_context():
        task = db.session.get(BidReviewTask, task_id)
        if not task:
            return
        try:
            task.status = "ocr_proc_doc"
            task.error_msg = ""
            task.progress = ""
            db.session.commit()
            md = _doc_to_md(task.proc_doc_path, task.proc_doc_name)
            task.proc_doc_ocr_md = md
            task.status = "extracting"
            task.updated_at = _now()
            db.session.commit()

            _, warnings = _extract_all(task, usage_ctx)
            task.status = "criteria_ready"
            # 部分类别失败时记入 error_msg 作提示（状态仍可用）
            task.error_msg = "；".join(warnings)
            task.progress = ""
            task.updated_at = _now()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            task = db.session.get(BidReviewTask, task_id)
            task.status = "failed"
            task.error_msg = f"{e}"
            task.progress = ""
            task.updated_at = _now()
            db.session.commit()


# ── ② 投标文件：OCR + 分批扫描（判定+评分）+ 报价抽取 ──────────────────
SCAN_SYSTEM = (
    "你是医院政府采购评审专家助手，在投标（响应）文件中为审查条目定位证据并按规则初判。\n"
    "【政府采购承诺制——判定基础，务必遵守】\n"
    "① 若采购条目【要求提供佐证材料】（如检测报告、证书、复印件、备案凭证、审计报告等）："
    "到投标文件中找该佐证。分三种情况：(a) 完全未提供任何相关材料、或佐证明显与要求矛盾/数值明显不达标 → 判「不满足」；"
    "(b) 提供了对应材料且明显达标 → 判「满足」；"
    "(c) 提供了材料、但该条采购要求对材料有附加合规条件（如『检测报告须完整、无PS遮挡截取、产品/包装信息与响应产品一致』『经营范围须与采购品类一致』『证明须在有效期内/时间相符』等），"
    "而你无法仅凭文本确信材料完整满足这些条件 → 判「需核验」（材料在、但完整性/合规性需人工核验），不要硬判满足或不满足。\n"
    "② 若采购条目【未要求提供佐证】：供应商只要在技术/商务应答（响应）表中作出「响应/承诺」即判「满足」——"
    "采购是承诺制，默认材料真实，无需也不应苛求额外证据。\n"
    "③ 例外（裁量）：佐证材料中明显显示不满足要求，但供应商应答表却写「响应」的，判「不满足」。\n"
    "④ 投标文件中完全找不到该条对应的响应或材料，才判「未找到」。切忌把「该条未要求佐证、供应商已响应」误判为不满足。\n"
    "⑤ 条目若带【应提交格式文件】（如『具有健全财务会计制度的证明材料.docx』『中小企业声明函』），"
    "优先在投标文件中定位同名文件核验——合并文本中各文件以『【投标文件：文件名】』标记分隔。\n"
    "⑥ 条目带【具体标准和要求】时，据其判断是否要求佐证：写明『提供…复印件/报告/证明/凭证/声明函』即要求佐证；写『填写《投标（响应）函》承诺』即承诺制、无需佐证。\n"
    "⑦ 重要：你每次只看到投标文件的一部分（若干页）。若本片段中找不到某条的响应或材料，"
    "一律输出 found=false（未找到），【不要】因为本片段没有就判「不满足」——材料可能在其他片段。"
    "只有本片段中出现明确相反/不达标证据时，才判「不满足」。\n"
    "【打分项·客观分】技术参数等客观分须逐条核对投标方「技术参数响应表/偏离表」的『响应/偏离』列，"
    "并结合检测报告等佐证：得分=满分−每个负偏离项的扣分（按评分规则）；负偏离=供应商自己标注负偏离、"
    "或填报/佐证数值低于采购要求。不得因为存在响应表就默认给满分。\n"
    "【打分项·主观分】方案类、服务类等主观分一律从宽：只要供应商提供了对应方案/响应内容，即给满分或接近满分，"
    "写得好坏、详略繁简都不影响给分（主观分是『有就给』）；不得臆造缺陷、不得用客观参数的偏离逻辑去苛扣；"
    "仅当评分规则要求的某项内容完全缺失、或整体空泛到与本项目无关时，才就该缺项酌情扣分。"
    "最终判定与得分由评审人员复核。"
)

SCAN_USER_TMPL = (
    "【审查条目清单】每条带类别标签（条目原文里若含『须提供…佐证/检测报告/证明』即为要求佐证）：\n{criteria}\n\n"
    "【投标文件片段】第{p_start}页至第{p_end}页，每页开头有 <!--page:N--> 页码标记：\n{body}\n\n"
    "按承诺制规则逐条判定/打分，输出 JSON（每条一项，按 criteria_seq 对应）：\n"
    '{{"hits": [\n'
    '  {{"criteria_seq": 1, "found": true, "verdict": "满足", "evidence_page": "第12页", '
    '"evidence_text": "原文摘录(不超过150字)", "confidence": "高"}},\n'
    '  {{"criteria_seq": 21, "found": true, "score": 8, "reason": "扣分理由：核对响应/偏离列，列出负偏离项(80字内)", '
    '"evidence_page": "第88页", "evidence_text": "原文摘录", "confidence": "中"}}\n'
    "]}}\n"
    "规则：[资格]/[实质性]/[商务] 条目填 verdict（只能是 满足/不满足/需核验/未找到），不填 score；"
    "（需核验=要求佐证的材料已提供，但完整性/合规性须人工核验，见系统规则①c）"
    "[打分] 条目填 score（0 到该项满分之间的数字）和 reason，不填 verdict；"
    "found=false 时其余字段留空；confidence 只能是 高/中/低；"
    "evidence_page 必须依据页码标记；只输出 JSON。"
)

# 第二轮聚焦复检追加的提示：这些条目初扫未找到，要求更仔细地重新查找
SCAN_RECHECK_NOTE = (
    "\n\n【二次聚焦复检】以上条目在初次扫描中未在投标文件里找到响应或材料。"
    "请对本片段【逐条更仔细地重新查找】：留意同义/近义表述、不同章节、表格内措辞、"
    "以及以格式文件名（如《中小企业声明函》）形式出现的材料。"
    "确有响应/材料才据实判定/打分；本片段中仍无对应内容的，继续 found=false。"
)

# 扫描返回的 JSON 契约：强制各模型用统一字段名（criteria_seq/found/verdict/score…），
# 避免 gemini 等自造字段(如"审查项/结论")导致命中被丢弃。支持的模型走
# response_format=json_schema 严格约束；不支持者自动降级为提示词约束。
SCAN_SCHEMA = {
    "type": "object",
    "properties": {
        "hits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criteria_seq": {"type": "integer"},
                    "found": {"type": "boolean"},
                    "verdict": {"type": "string"},
                    "score": {"type": "number"},
                    "reason": {"type": "string"},
                    "evidence_page": {"type": "string"},
                    "evidence_text": {"type": "string"},
                    "confidence": {"type": "string"},
                },
                "required": ["criteria_seq", "found"],
            },
        }
    },
    "required": ["hits"],
}


_CONF_RANK = {"高": 3, "中": 2, "低": 1, "": 0}
# 分批合并优先级：满足(明确达标) > 需核验(材料在但合规性待核) > 不满足(有相反证据) > 未找到(本批无)
# 需核验 高于 不满足：避免某批"没读全"误判不满足盖过另一批"材料在、待核验"
_VERDICT_RANK = {"满足": 3, "需核验": 2, "不满足": 1, "未找到": 0, "": 0}


def _crit_line(c):
    """条件清单中一行的文本（带类别标签；打分项带满分与细则节选）。"""
    if c.category == "打分":
        rule = (c.score_rule or "").strip()[:600]
        ms = f"{c.max_score:g}" if c.max_score is not None else "?"
        line = f"{c.seq}. [打分｜满分{ms}分] {c.content}"
        return f"{line}：{rule}" if rule else line
    return f"{c.seq}. [{c.category}] {c.content}"


def _crit_groups(criteria_rows):
    """条件清单过长时按 判定类/打分类 拆成两组分别跑批（控制单次 prompt 体积）。"""
    total = sum(len(_crit_line(c)) for c in criteria_rows)
    if total <= CRIT_TEXT_LIMIT:
        return [criteria_rows]
    judge = [c for c in criteria_rows if c.category != "打分"]
    score = [c for c in criteria_rows if c.category == "打分"]
    return [g for g in (judge, score) if g]


def _merge_hit(h, seq2id, id2crit, best):
    """把一条 hit 并入 best（择优保留）。返回是否被采纳。"""
    if not isinstance(h, dict):
        return False
    cid = seq2id.get(h.get("criteria_seq"))
    if not cid or not h.get("found"):
        return False
    c = id2crit[cid]
    prev = best.get(cid)
    if c.category == "打分":
        # 建议分规范化：数字化、按满分截断、不低于 0
        try:
            sc = float(h.get("score"))
        except (TypeError, ValueError):
            return False
        sc = max(0.0, sc)
        if c.max_score is not None:
            sc = min(sc, c.max_score)
        h["score"] = sc
        # 合并：confidence 高者优先，平手取分高者（证据更充分）
        def s_rank(x):
            return (_CONF_RANK.get(x.get("confidence", ""), 0), x.get("score") or 0)
        if prev is None or s_rank(h) > s_rank(prev):
            best[cid] = h
            return True
    else:
        # 合并：分批扫描下「满足」(在某批找到正面证据)优先于「不满足」，
        # 「不满足」优先于「未找到」。因为某批不含该材料时只是「未找到」，
        # 不应否决另一批已找到的「满足」（承诺制：找到即认）。
        def v_rank(x):
            return (_VERDICT_RANK.get(x.get("verdict", ""), 0),
                    _CONF_RANK.get(x.get("confidence", ""), 0))
        if prev is None or v_rank(h) > v_rank(prev):
            best[cid] = h
            return True
    return False


def _scan_pass(criteria_rows, batches, id2crit, best, usage_ctx, recheck, prog):
    """对 criteria_rows 遍历全部批次扫描一遍，命中并入 best。
    recheck=True 时追加二次聚焦复检提示。prog() 每完成一批调用一次。
    """
    for group in _crit_groups(criteria_rows):
        crit_text = "\n".join(_crit_line(c) for c in group)
        seq2id = {c.seq: c.id for c in group}
        for batch in batches:
            body = "\n\n".join(f"<!--page:{no}-->\n{txt}" for no, txt in batch)
            user = SCAN_USER_TMPL.format(criteria=crit_text, body=body,
                                         p_start=batch[0][0], p_end=batch[-1][0])
            if recheck:
                user += SCAN_RECHECK_NOTE
            try:
                out = chat_json(SCAN_SYSTEM, user, temperature=0.1,
                                max_tokens=8192, timeout=300, usage_ctx=usage_ctx,
                                response_schema=SCAN_SCHEMA)
            except Exception:
                # 单批失败不致命：跳过本批（相当于该批未提供证据），继续后续批次
                out = {"hits": []}
            hits = out if isinstance(out, list) else (out.get("hits") or [])
            for h in hits:
                _merge_hit(h, seq2id, id2crit, best)
            prog()


def _scan_batches(criteria_rows, pages, usage_ctx, on_progress=None,
                  max_rounds=BR_MAX_ROUNDS):
    """分批扫描全部页，返回 {criteria_id: best_hit_dict}。

    判定类 hit 含 verdict；打分类 hit 含 score/reason（已按满分截断）。

    闭环：初扫（全部条目×全部页）后做充分性检查——仍「未找到」的条目（best 中无记录）
    再做最多 max_rounds-1 轮聚焦复检（只带未找到条目重扫，注意力集中以捞回漏看的响应/材料）；
    仍找不到的即真·未找到，由调用方记为「未找到」交人工复核。
    """
    id2crit = {c.id: c for c in criteria_rows}
    best = {}
    batches = [pages[i:i + PAGES_PER_BATCH] for i in range(0, len(pages), PAGES_PER_BATCH)]

    # 进度：初扫按 组数×批数 计；触发复检时把额外步数累加进 total
    state = {"step": 0, "total": len(_crit_groups(criteria_rows)) * len(batches)}

    def prog():
        state["step"] += 1
        if on_progress:
            on_progress(state["step"], state["total"])

    # 第 1 轮：全部条目 × 全部页
    _scan_pass(criteria_rows, batches, id2crit, best, usage_ctx, False, prog)

    # 充分性检查 → 对未找到条目聚焦复检（最多 max_rounds-1 轮，仅在确有未找到时触发）
    for _ in range(max(0, max_rounds - 1)):
        unfound = [c for c in criteria_rows if c.id not in best]
        if not unfound:
            break
        state["total"] += len(_crit_groups(unfound)) * len(batches)
        _scan_pass(unfound, batches, id2crit, best, usage_ctx, True, prog)

    return best


PRICE_KEYWORDS = ["开标一览表", "报价一览", "投标函", "报价表", "总报价", "投标总价",
                  "报价函", "响应函"]

PRICE_USER_TMPL = (
    "以下是投标（响应）文件 OCR 文本节选，每页开头有 <!--page:N--> 页码标记。\n"
    "请找出本投标文件的总报价（开标一览表/投标函/报价表中的投标总价，含税口径优先），"
    "输出 JSON：\n"
    '{{"bid_price": "1234567.00", "page": "第3页", "note": "口径说明，如 含税总价"}}\n'
    "bid_price 只填数字（单位：元，可带小数，不要千分位逗号）；找不到填空字符串；"
    "只输出 JSON，不要其他文字。\n\n"
    "【投标文件文本】\n{doc}"
)


def _extract_price(res, pages, usage_ctx):
    """抽取总报价写入 result（失败静默；人工改过价则由调用方跳过）。"""
    try:
        out = chat_json(
            "你是医院采购评审专家助手，负责从投标文件中找出投标总报价。",
            PRICE_USER_TMPL.format(
                doc=_select_pages(pages, PRICE_KEYWORDS, budget=30000,
                                  query="开标一览表、投标函、报价表中的投标总报价/总价")),
            temperature=0, max_tokens=1024, timeout=180, usage_ctx=usage_ctx)
        if not isinstance(out, dict):
            return
        price = str(out.get("bid_price") or "").strip().replace(",", "").replace("，", "")
        if re.fullmatch(r"\d+(\.\d+)?", price):
            res.bid_price = price
            res.price_page = str(out.get("page") or "").strip()[:30]
    except Exception:
        pass


def _supplier_files(res):
    """该投标方的文件列表 [(name, path), ...]；兼容旧的单文件 result。"""
    files = db.session.execute(
        db.select(BidReviewResultFile).filter_by(result_id=res.id)
        .order_by(BidReviewResultFile.seq, BidReviewResultFile.id)
    ).scalars().all()
    if files:
        return [(f.file_name, f.file_path) for f in files]
    if res.file_path:
        return [(res.bid_file_name, res.file_path)]
    return []


def _merge_docs(files):
    """多文件按顺序转文本，连续编全局页码；每个文件首页前加文件标记，
    便于模型/人工区分证据来自哪份文件。返回带 <!--page:N--> 的合并文本。"""
    out, gp = [], 0
    for name, path in files:
        md = _doc_to_md(path, name)
        for idx, (_, txt) in enumerate(split_pages(md)):
            gp += 1
            head = f"【投标文件：{name}】\n" if idx == 0 else ""
            out.append(f"<!--page:{gp}-->\n{head}{txt}")
    return "\n\n".join(out)


def _scan_via_service(criteria_rows, pages_md):
    """调容器化审核服务(9010)扫描，返回 {criteria_id: hit}（同 _scan_batches 格式，仅命中项）。
    9010 内部走 llm-gateway；失败抛异常由调用方本地兜底。"""
    crit = [{"id": c.id, "category": c.category, "content": c.content,
             "max_score": c.max_score, "score_rule": c.score_rule or ""}
            for c in criteria_rows]
    r = requests.post(f"{BID_REVIEW_SVC}/review",
                      json={"criteria": crit, "pages_md": pages_md}, timeout=1800)
    r.raise_for_status()
    d = r.json()
    if not d.get("ok"):
        raise RuntimeError(d.get("error", "审核服务返回错误"))
    best = {}
    for row in d.get("results", []):
        cid = row.get("id")
        base = {"evidence_page": row.get("evidence_page", ""),
                "evidence_text": row.get("evidence_text", ""),
                "confidence": row.get("confidence", "")}
        if row.get("category") == "打分":
            if row.get("score") is not None:
                best[cid] = {**base, "score": row["score"], "reason": row.get("reason", "")}
        else:
            v = row.get("verdict")
            if v and v != "未找到":
                best[cid] = {**base, "verdict": v}
    return best


def review_bid_file(app, result_id, usage_ctx):
    """后台线程：投标文件（多文件合并）OCR → 分批扫描 → 报价抽取 → 写逐条明细。"""
    with app.app_context():
        res = db.session.get(BidReviewResult, result_id)
        if not res:
            return
        try:
            # 1) 识别合并（已有结果则复用；文件增删时调用方会清空 ocr_md 触发重跑）
            if not res.ocr_md:
                res.ocr_status = "running"
                res.error_msg = ""
                db.session.commit()
                files = _supplier_files(res)
                if not files:
                    raise RuntimeError("该投标方未上传任何文件")
                res.ocr_md = _merge_docs(files)
            res.ocr_status = "done"
            res.status = "running"
            res.updated_at = _now()
            db.session.commit()

            task = db.session.get(BidReviewTask, res.task_id)
            # 适用条目：通用 + 所投包；打分项仅综合评分法纳入
            rows = db.session.execute(
                db.select(BidReviewCriteria).filter_by(task_id=res.task_id)
                .order_by(BidReviewCriteria.seq)
            ).scalars().all()
            lot = res.lot_no or LOT_COMMON
            criteria_rows = [
                c for c in rows
                if (c.lot_no or LOT_COMMON) in (LOT_COMMON, lot)
                and (c.category != "打分" or task.eval_method == "综合评分法")
            ]
            if not criteria_rows:
                raise RuntimeError("适用该包的条目清单为空，请先在任务中确认条目")

            pages = split_pages(res.ocr_md)

            def on_progress(done, total):
                r = db.session.get(BidReviewResult, result_id)
                r.progress = f"{done}/{total} 批"
                db.session.commit()

            r0 = db.session.get(BidReviewResult, result_id)
            r0.progress = "审核服务处理中…"
            db.session.commit()
            try:
                best = _scan_via_service(criteria_rows, res.ocr_md)
            except Exception as _svc_err:
                # 9010 不可用 → 本地兜底扫描，保证审核不中断
                best = _scan_batches(criteria_rows, pages, usage_ctx, on_progress)

            # 2) 报价抽取（人工改过价则不覆盖）
            if not res.price_edited_by:
                _extract_price(res, pages, usage_ctx)

            # 3) 写明细（重跑时先清旧，会覆盖此前的人工改判/改分）
            db.session.execute(db.delete(BidReviewResultItem).where(
                BidReviewResultItem.result_id == result_id))
            for c in criteria_rows:
                h = best.get(c.id)
                common = dict(
                    result_id=result_id, criteria_id=c.id,
                    evidence_page=(h.get("evidence_page") or "") if h else "",
                    evidence_text=(h.get("evidence_text") or "")[:1000] if h else "",
                    confidence=(h.get("confidence") or "") if h else "",
                )
                if c.category == "打分":
                    sc = h.get("score") if h else None
                    db.session.add(BidReviewResultItem(
                        verdict="", ai_score=sc, final_score=sc,
                        ai_reason=(h.get("reason") or "")[:500] if h else "",
                        **common))
                else:
                    db.session.add(BidReviewResultItem(
                        verdict=(h.get("verdict") if h else "未找到") or "未找到",
                        **common))
            res = db.session.get(BidReviewResult, result_id)
            res.status = "done"
            res.updated_at = _now()
            db.session.commit()

            # 任务下全部投标文件审完 → 任务置 done
            task = db.session.get(BidReviewTask, res.task_id)
            siblings = db.session.execute(
                db.select(BidReviewResult).filter_by(task_id=res.task_id)
            ).scalars().all()
            if task and all(s.status == "done" for s in siblings):
                task.status = "done"
                task.updated_at = _now()
                db.session.commit()
        except Exception as e:
            db.session.rollback()
            res = db.session.get(BidReviewResult, result_id)
            if res.ocr_status == "running":
                res.ocr_status = "failed"
            res.status = "failed"
            res.error_msg = f"{e}"
            res.updated_at = _now()
            db.session.commit()


# ── 线程启动入口 ───────────────────────────────────────────────────────
def start_proc_doc_thread(app, task_id, usage_ctx):
    threading.Thread(target=process_proc_doc, args=(app, task_id, usage_ctx),
                     daemon=True).start()


def start_review_thread(app, result_id, usage_ctx):
    threading.Thread(target=review_bid_file, args=(app, result_id, usage_ctx),
                     daemon=True).start()
