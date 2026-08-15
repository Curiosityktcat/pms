"""以科室账号身份把所有无参数 GET 接口打一遍，看谁会吐出本科室之外的数据。

新角色接进成熟系统，最大的风险不是门户写错，而是几十个老接口里散落的
「认识 officer/agency 就过滤，其余默认放行」。这个扫描就是来找它们的。
只打 GET、只打无路径参数的、跳过会触发外部动作的模块。
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/pms/backend"))

import app as A
from models import db
from models.project import Project
from services import dept as dept_svc

# 会连外网/起浏览器/跑模型的，别在扫描里碰
SKIP_PREFIX = ("/api/rdweb", "/api/hermes", "/api/ccgp", "/api/ocr", "/api/ai",
               "/api/datapipe", "/api/llm", "/api/scraper", "/api/presence",
               "/api/tools", "/api/office", "/static")

a = A.create_app()
with a.app_context():
    names = dept_svc.dept_names("SBK")
    visible = {p.id for p in db.session.execute(
        db.select(Project).where(db.or_(Project.manage_dept.in_(names),
                                        Project.demand_dept.in_(names)))
    ).scalars()}
    all_ids = {p.id for p in db.session.execute(db.select(Project)).scalars()}
outside_ids = all_ids - visible

c = a.test_client()
with c.session_transaction() as s:
    s["user"] = "医学装备部"; s["role"] = "dept"; s["dept_code"] = "SBK"
    s["agency_code"] = ""; s["display_name"] = "医学装备部"

rules = sorted({str(r) for r in a.url_map.iter_rules()
                if "GET" in (r.methods or set()) and "<" not in str(r)
                and str(r).startswith("/api/")
                and not str(r).startswith(SKIP_PREFIX)})

print("扫描 %d 个无参数 GET 接口\n" % len(rules))
suspects = []
for path in rules:
    if path.startswith("/api/dept/"):
        continue          # 门户自身已由冒烟覆盖
    try:
        r = c.get(path)
    except Exception as e:
        print("  %-46s 异常 %s" % (path, type(e).__name__))
        continue
    if r.status_code != 200 or not r.is_json:
        continue
    body = r.get_json()
    if not isinstance(body, dict):
        continue
    rows = body.get("data")
    if not isinstance(rows, list) or not rows:
        continue
    # 行里带项目 id 的，检查有没有越出本科室
    leaked = 0
    for x in rows:
        if not isinstance(x, dict):
            continue
        pid = x.get("project_id") or x.get("id")
        if isinstance(pid, int) and pid in outside_ids and "project" in str(x.keys()).lower() + path:
            leaked += 1
    flag = "  ← 可疑" if leaked else ""
    print("  %-46s 200  %4d 行  越界 %d%s" % (path, len(rows), leaked, flag))
    if leaked:
        suspects.append((path, len(rows), leaked))

print()
if suspects:
    print("需要人工确认的接口：")
    for p, n, k in suspects:
        print("   %s  共 %d 行，其中 %d 行不属于本科室" % (p, n, k))
else:
    print("没有发现越界返回。")
