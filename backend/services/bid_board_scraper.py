#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
开标看板抓取服务（迁移自 test/venv/scraper.py）。

流程：翻页抓医院官网列表 → 逐条详情交本机大模型提取4字段+判断是否正式招标
      → 解析截止时间 → 筛未来14天内截止 → 写入 bid_board_projects（不覆盖 supervisor）

依赖本机大模型 API（192.168.1.10:8888）与外网访问 njyy.com.cn。
由 routes/bid_board_api.py 的「手动刷新」在后台线程内调用 run_scrape(app)。
"""

import re
import ssl
import json
import time
import datetime

import requests
import urllib3
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from models import db
from models.bid_board_project import BidBoardProject
from models.sys_config import SysConfig

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
# 全局禁用 SSL 证书校验（本地缺根证书 + 公开公告，无安全风险）
ssl._create_default_https_context = ssl._create_unverified_context
_orig_get = requests.get


def _get_noverify(*a, **k):
    k.setdefault("verify", False)
    return _orig_get(*a, **k)


requests.get = _get_noverify

# ---------- 配置 ----------
BASE = "https://www.njyy.com.cn"
LIST_P1 = "https://www.njyy.com.cn/News/lists/id/34.html"
LIST_PN = "https://www.njyy.com.cn/News/lists/p/{p}/id/34.html"
DETAIL_PAT = re.compile(r"/News/info/id/\d+\.html")

MAX_PAGES = 4          # 最多翻几页（够覆盖14天即可）
WINDOW_DAYS = 14       # 只要未来这么多天内截止的

# 模型默认值（本机大模型）。可在「抓取模型设置」中改为在线模型。
DEFAULT_MODEL_API = "http://192.168.1.10:8888/v1/chat/completions"
DEFAULT_MODEL_NAME = "qwen36-apex-mtp-mini"
DEFAULT_API_KEY = "local"

# SysConfig 键名
CFG_MODEL_API = "scraper_model_api"
CFG_MODEL_NAME = "scraper_model_name"
CFG_API_KEY = "scraper_api_key"


def get_model_config():
    """从 SysConfig 读取模型配置，缺省回落到本机大模型默认值。
    需在 Flask app 上下文内调用。"""
    def _val(key, default):
        row = db.session.get(SysConfig, key)
        return (row.value if row and row.value else default)
    return {
        "api":  _val(CFG_MODEL_API,  DEFAULT_MODEL_API),
        "name": _val(CFG_MODEL_NAME, DEFAULT_MODEL_NAME),
        "key":  _val(CFG_API_KEY,    DEFAULT_API_KEY),
    }

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9",
}

SYSTEM_PROMPT = """你是一个采购公告信息提取助手。我会给你一篇公告的正文。
请严格按公告原文提取信息，绝对不要猜测或编造，原文没有写的就填"无"。

请判断这篇公告是否为【正式竞选/招标公告】：
- 正式竞选/招标：有明确的"递交响应文件截止时间"或"开标时间"，供应商可以投标。
- 非正式（需排除）：市场调研公告、更正公告、单一来源采购公示、结果公示等。

只输出一个 JSON 对象，不要任何其他文字、不要 markdown 代码块：
{"is_tender": true/false, "name": "采购项目名称", "number": "采购项目编号", "agency": "代理公司全称", "deadline": "递交响应文件截止时间"}

要求：
- is_tender: 是正式竞选/招标填 true，否则 false。
- name: 采购项目名称。(1)去掉开头"内江市第一人民医院"前缀；(2)去掉末尾"院内竞选公告""采购项目"等后缀和标点；(3)若是第几次招标(如"第二次""（二次）")，在名称末尾用括号保留，如"2026年手消毒剂一批采购（第二次）"。
- number: 采购项目编号，没有填"无"。
- agency: 代理公司完整公司名，没有填"无"。
- deadline: 递交响应文件截止时间，保留原文(如 2026年5月27日16:00)，没有填"无"。

/no_think"""


def fetch(url, retries=3):
    """带重试，关闭证书校验（公开公告，无敏感数据，避免本地缺根证书报错）。"""
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=25, verify=False)
            r.raise_for_status()
            if r.encoding is None or r.encoding.lower() == "iso-8859-1":
                r.encoding = r.apparent_encoding
            return r.text
        except Exception as e:
            last = e
            time.sleep(1.5 * (attempt + 1))  # 递增等待，扛网络抖动
    raise last


def get_links(html):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        if DETAIL_PAT.search(a["href"]):
            u = urljoin(BASE, a["href"])
            if u not in seen:
                seen.add(u)
                out.append((a.get_text(strip=True), u))
    return out


def detail_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style"]):
        t.decompose()
    return soup.get_text("\n", strip=True)[:3000]


def _model_post(cfg, text, with_extras):
    """单次请求。with_extras=True 时带上本机模型专用的 chat_template_kwargs；
    通用在线模型不认这些字段会返回 4xx，此时由调用方降级重试。"""
    payload = {
        "model": cfg["name"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"公告正文如下：\n\n{text}"},
        ],
        "temperature": 0,
        "max_tokens": 1200,
    }
    if with_extras:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    return requests.post(
        cfg["api"],
        headers={"Authorization": f"Bearer {cfg['key']}",
                 "Content-Type": "application/json"},
        json=payload, timeout=120,
    )


def ask_model(text, cfg, retries=2):
    last = None
    with_extras = True
    for _ in range(retries + 1):
        try:
            r = _model_post(cfg, text, with_extras)
            # 通用在线模型可能因 chat_template_kwargs 等扩展字段报 400/422，
            # 去掉扩展字段后再试一次。
            if r.status_code in (400, 422) and with_extras:
                with_extras = False
                r = _model_post(cfg, text, with_extras)
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            c = (msg.get("content") or "").strip()
            if not c and msg.get("reasoning_content"):
                c = msg["reasoning_content"].strip()
            c = re.sub(r"^```(json)?|```$", "", c, flags=re.MULTILINE).strip()
            m = re.search(r"\{.*\}", c, re.DOTALL)
            if m:
                return json.loads(m.group(0))
        except Exception as e:
            last = e
            time.sleep(1)
    raise RuntimeError(f"模型提取失败: {last}")


def parse_deadline(s):
    if not s or s == "无":
        return None
    m = re.search(r"(\d{4})\D+(\d{1,2})\D+(\d{1,2})\D*(?:(\d{1,2})[:：](\d{1,2}))?", s)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = int(m.group(4)) if m.group(4) else 23
    mm = int(m.group(5)) if m.group(5) else 59
    try:
        return datetime.datetime(y, mo, d, hh, mm)
    except ValueError:
        return None


def _scrape_window(cfg):
    """执行抓取，返回（窗口内项目列表, 未解析列表, 跳过非招标数）。不写库。"""
    now = datetime.datetime.now()
    window_end = now + datetime.timedelta(days=WINDOW_DAYS)
    print(f"[*] {now:%Y-%m-%d %H:%M} 开始抓取，窗口 未来{WINDOW_DAYS}天")

    # 收集详情链接（翻页）
    links, seen = [], set()
    for p in range(1, MAX_PAGES + 1):
        url = LIST_P1 if p == 1 else LIST_PN.format(p=p)
        try:
            page_links = get_links(fetch(url))
        except Exception as e:
            print(f"[!] 第{p}页失败: {e}")
            break
        for t, u in page_links:
            if u not in seen:
                seen.add(u)
                links.append((t, u))
        print(f"[*] 第{p}页 累计 {len(links)} 条")

    in_window, unparsed, skipped = [], [], 0
    for i, (title, url) in enumerate(links, 1):
        try:
            info = ask_model(detail_text(fetch(url)), cfg)
        except Exception as e:
            print(f"  [{i}] 失败: {e}")
            unparsed.append({"name": title, "number": "?", "agency": "?",
                             "deadline": "(提取失败)", "url": url})
            continue
        if not info.get("is_tender"):
            skipped += 1
            time.sleep(0.3)
            continue
        info["url"] = url
        dl = parse_deadline(info.get("deadline", ""))
        if dl is None:
            unparsed.append(info)
        elif now <= dl <= window_end:
            info["deadline_iso"] = dl.isoformat()
            in_window.append(info)
        # 过期/超窗的丢弃（不在14天窗口内）
        time.sleep(0.3)

    in_window.sort(key=lambda x: x["deadline_iso"])
    return in_window, unparsed, skipped


def _save(in_window):
    """写入数据库：更新已有项目时不覆盖 supervisor 人工字段。返回 (新增, 更新)。"""
    nowiso = datetime.datetime.now().isoformat()
    inserted, updated = 0, 0
    for it in in_window:
        num = (it.get("number") or "").strip()
        if not num or num == "无":
            # 没有编号的项目无法做唯一识别，用 url 兜底当编号，避免丢失
            num = "URL:" + it.get("url", "")
        row = db.session.get(BidBoardProject, num)
        if row:
            # 只更新抓取字段，supervisor 那一列原样保留
            row.name = it.get("name", "")
            row.agency = it.get("agency", "")
            row.deadline = it.get("deadline", "")
            row.deadline_iso = it.get("deadline_iso", "")
            row.url = it.get("url", "")
            row.updated_at = nowiso
            updated += 1
        else:
            db.session.add(BidBoardProject(
                number=num,
                name=it.get("name", ""),
                agency=it.get("agency", ""),
                deadline=it.get("deadline", ""),
                deadline_iso=it.get("deadline_iso", ""),
                url=it.get("url", ""),
                supervisor="",
                first_seen=nowiso,
                updated_at=nowiso,
            ))
            inserted += 1

    # 记录元数据（供页面显示「更新于」）
    for k, v in (("bid_board_last_run", nowiso),
                 ("bid_board_window_days", str(WINDOW_DAYS))):
        cfg = db.session.get(SysConfig, k)
        if cfg:
            cfg.value = v
            cfg.updated_at = nowiso
        else:
            db.session.add(SysConfig(key=k, value=v, updated_at=nowiso))

    db.session.commit()
    return inserted, updated


def run_scrape(app):
    """在后台线程内调用：需要 Flask app 以建立应用上下文访问数据库。

    返回结果描述字符串。
    """
    with app.app_context():
        cfg = get_model_config()
        in_window, unparsed, skipped = _scrape_window(cfg)
        inserted, updated = _save(in_window)
        msg = (f"完成: 14天内 {len(in_window)} 条 (新增{inserted}/更新{updated}), "
               f"待确认 {len(unparsed)}, 跳过非招标 {skipped}")
        print(f"[*] {msg}")
        return msg
