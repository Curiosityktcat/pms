#!/usr/bin/env python3
"""清掉冒烟测试写进生产库的假驳回记录（默认只看不删）。

来历：测试脚本把 project_id 写死成 12，留下 17 条 reason 为「冒烟测试…」的
驳回，target_id 指向的公告其实属于别的项目。考核算分已经不认这类记录了
（services/agency_assessment.py 会核对公告归属），但它们还会出现在项目的
审批记录里，看着像真被驳回过 17 次。

用法：
    python3 clean_smoke_logs.py              # 只列出要删的，什么都不动
    python3 clean_smoke_logs.py --apply      # 备份后真删
"""
import datetime
import shutil
import sqlite3
import sys

DBS = ["/home/huangxb/pms/pms.db", "/home/huangxb/pms/pms.test.db"]
COND = """action='reject' AND reason LIKE '冒烟测试%'
      AND target_id NOT IN (SELECT id FROM announcements a
                            WHERE a.project_id = approval_logs.project_id)"""

apply = "--apply" in sys.argv
for f in DBS:
    c = sqlite3.connect(f)
    rows = c.execute(f"SELECT id, project_id, target_id, created_at, reason "
                     f"FROM approval_logs WHERE {COND}").fetchall()
    print(f"\n{f}：命中 {len(rows)} 条")
    for r in rows[:5]:
        print("   ", r)
    if len(rows) > 5:
        print(f"    …另外 {len(rows) - 5} 条")
    if apply and rows:
        bak = f + ".bak.smoke_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(f, bak)
        print("    已备份到", bak)
        c.execute(f"DELETE FROM approval_logs WHERE {COND}")
        c.commit()
        print("    已删除", len(rows), "条")
    c.close()

if not apply:
    print("\n以上只是列出。确认无误后加 --apply 才会备份并删除。")
