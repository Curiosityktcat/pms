#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import laws_export.json into the PMS `laws` table.
Run from ~/pms:  PMS_DB_PATH=/home/huangxb/pms/pms.test.db venv/python import_laws.py laws_export.json
Reference data -> wipes & reloads the laws table (idempotent)."""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend"))

from flask import Flask
from models import db
from models.law import Law

DB = os.environ.get("PMS_DB_PATH") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "pms.db"))
EXPORT = sys.argv[1] if len(sys.argv) > 1 else "laws_export.json"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.abspath(DB)}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)

FIELDS = {c.name for c in Law.__table__.columns}

with app.app_context():
    db.create_all()  # creates `laws` table if missing (only Law in metadata here)
    n_old = Law.query.count()
    Law.query.delete()
    data = json.load(open(EXPORT, encoding="utf-8"))
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in data:
        rec = {k: v for k, v in r.items() if k in FIELDS}
        rec.setdefault("created_at", now)
        db.session.add(Law(**rec))
    db.session.commit()
    print(f"laws table: {n_old} -> {Law.query.count()} (DB={os.path.abspath(DB)})")
    # quick sanity
    print("  catalog-tagged:", Law.query.filter(Law.catalog_num.isnot(None)).count())
    by = {}
    from sqlalchemy import func
    for lv, c in db.session.query(Law.level, func.count(Law.id)).group_by(Law.level).all():
        by[lv or "未分类"] = c
    print("  by level:", by)
