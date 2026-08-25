# -*- coding: utf-8 -*-
"""对跑着的测试实例 1574 验证标的表：列、行、修复后的数据。"""
import io
import sys

import requests
from flask.sessions import SecureCookieSessionInterface

BASE = "http://127.0.0.1:1574"
FAIL = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("✓" if cond else "✗", name, ("  → " + str(detail)) if detail else ""))
    if not cond:
        FAIL.append(name)


class F:
    def __init__(self, k):
        self.secret_key = k
        self.config = {"SESSION_COOKIE_SALT": "cookie-session", "SECRET_KEY_FALLBACKS": None}
        self.session_cookie_name = "session"
        self.permanent_session_lifetime = None


sec = "change-this-secret-key-please"
ser = SecureCookieSessionInterface().get_signing_serializer(F(sec))
ck = ser.dumps({"user": "admin", "role": "assistant", "dept_code": "", "agency_code": "",
                "display_name": "采购部助理", "must_change_pw": 0, "_permanent": True})
s = requests.Session()
s.cookies.set("pms_test_session", ck)

r = s.get("%s/api/procurement-demands/18/doc-html" % BASE, timeout=20)
print("接口状态:", r.status_code)
if r.status_code != 200:
    print(r.text[:300])
    sys.exit(1)
doc = r.json().get("data") or r.json()
blocks = [b for sec_ in doc.get("sections", []) for b in sec_.get("blocks", [])
          if b.get("field") == "标的"]
check("标的块拿到", len(blocks) >= 1, "%d 个" % len(blocks))
top = blocks[0]
head = top.get("header") or []
cols = top.get("columns") or []
print("     表头:", "｜".join(head))
check("13 列表头", len(head) == 13, len(head))
check("12 列规范下发到前端", len(cols) == 12, len(cols))
check("含采购品目", "采购品目" in head)
check("含单价", "单价（元）" in head)
check("含合计金额", "合计金额（元）" in head)
check("含节能三问", "是否采购节能产品" in head and "是否采购环保产品" in head
      and "是否采购进口产品" in head)
check("含所属行业", "标的物所属行业" in head)

rows = top.get("rows") or []
print("     修复后的标的：")
for row in rows:
    print("       ", row)
check("坏数据已还原成 4 条", len(rows) == 4, len(rows))
if rows:
    check("第1条名称=手术机器人", rows[0][head.index("标的名称")] == "手术机器人",
          rows[0][head.index("标的名称")])
    check("名称列不再是数字", not str(rows[0][head.index("标的名称")]).isdigit())

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "; ".join(FAIL)))
    sys.exit(1)
print("跑着的 1574 上，标的表列已补齐、坏数据已还原")
