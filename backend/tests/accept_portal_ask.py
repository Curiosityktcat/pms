# -*- coding: utf-8 -*-
"""验收：确认发布不再自动挂官网，改为返回 can_portal 让前端弹框问（只打测试库）。"""
import os
import secrets
import sys

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
os.environ["PMS_CAPTCHA_ON"] = "0"
PW = "Ask!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c:
        ok += 1
        print(f"OK   {t} {e}")
    else:
        bad.append(t)
        print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.project import Project
from models.announcement import Announcement
from services.auth import hash_pw
from routes import njyy_portal_api as api

app = create_app()
app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

ann = db.session.execute(
    db.select(Announcement).filter_by(ann_type="procurement").order_by(Announcement.id.desc())
).scalars().first()
proj = db.session.get(Project, ann.project_id)
if not proj.officer:
    proj.officer = "弹框验收经办人"
    db.session.commit()

u = db.session.execute(db.select(User).filter_by(username="acc_ask_off")).scalar_one_or_none()
if u is None:
    u = User(username="acc_ask_off", display_name=proj.officer, role="officer",
             dept_code="", active=1, agency_code="", salt="", pw_hash="")
    db.session.add(u)
u.display_name, u.role, u.active = proj.officer, "officer", 1
salt = secrets.token_hex(16)
u.salt, u.pw_hash = salt, hash_pw(PW, salt)
if hasattr(u, "must_change_pw"):
    u.must_change_pw = 0
db.session.commit()

c = app.test_client()
c.post("/api/auth/login", json={"username": "acc_ask_off", "password": PW})

# 复位成待确认、没挂过
old = (ann.status, ann.portal_news_id, ann.portal_status, ann.portal_url)
ann.status, ann.portal_news_id, ann.portal_status, ann.portal_url = "待确认", 0, "", ""
db.session.commit()

started = {"n": 0}
real_start = api.start_publish
api.start_publish = lambda *a, **k: started.__setitem__("n", started["n"] + 1) or True

r = c.post(f"/api/announcements/{ann.id}/confirm")
body = r.get_json() or {}
check("① 确认发布成功", r.status_code == 200 and body.get("ok"), body.get("message", "")[:40])
check("② 没有自动去挂官网", started["n"] == 0, f"start_publish 被调了 {started['n']} 次")
check("③ 返回 can_portal=true 让前端弹框问", body.get("can_portal") is True, str(body.get("can_portal")))

# 已经挂过的就不该再问
ann.portal_news_id, ann.portal_url = 7777, "https://x/7777.html"
ann.status = "待确认"
db.session.commit()
r = c.post(f"/api/announcements/{ann.id}/confirm")
check("④ 已挂过官网的不再问", (r.get_json() or {}).get("can_portal") is False,
      str((r.get_json() or {}).get("can_portal")))

# 经办人点了「挂官网」→ 走的还是那个接口
ann.portal_news_id, ann.portal_url, ann.status = 0, "", "已确认"
db.session.commit()
r = c.post(f"/api/announcements/{ann.id}/portal/publish")
check("⑤ 点了挂官网才真的开跑",
      r.status_code == 200 and started["n"] == 1, f"HTTP {r.status_code}，start_publish {started['n']} 次")

api.start_publish = real_start
ann.status, ann.portal_news_id, ann.portal_status, ann.portal_url = old
db.session.commit()

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
