#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import catalog.json into the PMS `supervision_channels` table.
用法（在 PMS 根目录）：
  PMS_DB_PATH=/home/huangxb/pms/pms.test.db venv/python import_supervision.py catalog.json
参考数据 -> 清空并整表重载（幂等）。
"""
import os, sys, json, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from flask import Flask
from models import db
from models.supervision import SupervisionChannel

DB = os.environ.get("PMS_DB_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "pms.db"))
EXPORT = sys.argv[1] if len(sys.argv) > 1 else "catalog.json"
SRC_URL = "https://zhuanlan.zhihu.com/p/697136714"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath(DB)}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

FIELDS = {c.name for c in SupervisionChannel.__table__.columns}

with app.app_context():
    db.create_all()
    n_old = SupervisionChannel.query.count()
    SupervisionChannel.query.delete()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in json.load(open(EXPORT, encoding="utf-8")):
        rec = {k: v for k, v in r.items() if k in FIELDS}
        rec.setdefault("created_at", now)
        rec.setdefault("source_url", SRC_URL)
        db.session.add(SupervisionChannel(**rec))
    db.session.commit()
    n = SupervisionChannel.query.count()
    print(f"supervision_channels: {n_old} -> {n} (DB={os.path.abspath(DB)})")
    from sqlalchemy import func
    by = dict(db.session.query(SupervisionChannel.org_type,
                               func.count(SupervisionChannel.id))
              .group_by(SupervisionChannel.org_type).all())
    print("  by org_type:", by)
