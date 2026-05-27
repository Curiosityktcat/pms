#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 projects 加开标管理相关字段：can_open(能否开标) / bid_note(备注)。重复运行安全。"""
import os, sqlite3
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms.db")
conn = sqlite3.connect(DB)
cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
for col, ddl in [("can_open", "can_open TEXT DEFAULT ''"),     # ''未判定 / '可开标' / '流标'
                 ("bid_note", "bid_note TEXT DEFAULT ''")]:
    if col not in cols:
        conn.execute(f"ALTER TABLE projects ADD COLUMN {ddl}")
        print(f"[*] 已加 {col} 列")
    else:
        print(f"[*] {col} 已存在")
conn.commit(); conn.close()
