#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 projects 表补充 is_draft 列（草稿标记）。重复运行安全。"""
import os, sqlite3
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms.db")
conn = sqlite3.connect(DB)
cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
if "is_draft" not in cols:
    conn.execute("ALTER TABLE projects ADD COLUMN is_draft INTEGER DEFAULT 0")
    conn.commit()
    print("[*] 已添加 is_draft 列")
else:
    print("[*] is_draft 列已存在，无需改动")
conn.close()
