#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：把旧看板 procurement.db 的 projects 行导入 pms.db。

用法：python migrate_bid_board.py [旧库路径]
默认旧库 = ~/test/venv/procurement.db
重复运行安全：已存在的项目按编号更新抓取字段，但保留已指定的 supervisor。
"""
import os
import sys
import sqlite3

from app import create_app
from models import db
from models.bid_board_project import BidBoardProject
from models.sys_config import SysConfig

DEFAULT_OLD = os.path.expanduser("~/test/venv/procurement.db")


def main():
    old = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OLD
    if not os.path.exists(old):
        print(f"[!] 找不到旧库: {old}")
        sys.exit(1)

    src = sqlite3.connect(old)
    src.row_factory = sqlite3.Row
    rows = src.execute("SELECT * FROM projects").fetchall()
    meta = {r["k"]: r["v"] for r in src.execute("SELECT k, v FROM meta").fetchall()}
    src.close()

    app = create_app()
    with app.app_context():
        ins = upd = 0
        for r in rows:
            num = r["number"]
            existing = db.session.get(BidBoardProject, num)
            if existing:
                existing.name = r["name"]
                existing.agency = r["agency"]
                existing.deadline = r["deadline"]
                existing.deadline_iso = r["deadline_iso"]
                existing.url = r["url"]
                existing.updated_at = r["updated_at"]
                # 保留已有 supervisor；旧库有值且新库为空时补上
                if r["supervisor"] and not existing.supervisor:
                    existing.supervisor = r["supervisor"]
                upd += 1
            else:
                db.session.add(BidBoardProject(
                    number=num,
                    name=r["name"],
                    agency=r["agency"],
                    deadline=r["deadline"],
                    deadline_iso=r["deadline_iso"],
                    url=r["url"],
                    supervisor=r["supervisor"] or "",
                    first_seen=r["first_seen"],
                    updated_at=r["updated_at"],
                ))
                ins += 1

        # 迁移元数据
        for k_old, k_new in (("last_run", "bid_board_last_run"),
                             ("window_days", "bid_board_window_days")):
            if k_old in meta:
                cfg = db.session.get(SysConfig, k_new)
                if cfg:
                    cfg.value = meta[k_old]
                else:
                    db.session.add(SysConfig(key=k_new, value=meta[k_old], updated_at=""))

        db.session.commit()
        total = db.session.scalar(db.select(db.func.count()).select_from(BidBoardProject))
        print(f"[*] 迁移完成：新增 {ins} / 更新 {upd}，bid_board_projects 现有 {total} 条")


if __name__ == "__main__":
    main()
