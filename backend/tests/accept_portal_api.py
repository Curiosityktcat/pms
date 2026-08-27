# -*- coding: utf-8 -*-
"""挂网接口层验收（只打测试库，不真的动官网）：权限、状态机、字段回写。"""
import os
import secrets
import sys

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
os.environ["PMS_CAPTCHA_ON"] = "0"
PW = "Ptl!2026"
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


def acct(username, display, role):
    u = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if u is None:
        u = User(username=username, display_name=display, role=role, dept_code="",
                 active=1, agency_code="", salt="", pw_hash="")
        db.session.add(u)
    u.display_name, u.role, u.active = display, role, 1
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash = salt, hash_pw(PW, salt)
    if hasattr(u, "must_change_pw"):
        u.must_change_pw = 0
    db.session.commit()
    return username


def login(un):
    c = app.test_client()
    c.post("/api/auth/login", json={"username": un, "password": PW})
    return c


ann = db.session.execute(
    db.select(Announcement).filter_by(ann_type="procurement").order_by(Announcement.id.desc())
).scalars().first()
proj = db.session.get(Project, ann.project_id)
if not proj.officer:
    proj.officer = "挂网验收经办人"
    db.session.commit()
officer = acct("acc_portal_off", proj.officer, "officer")
agency = acct("acc_portal_ag", "四川三盈招标代理有限公司", "agency")
u = db.session.execute(db.select(User).filter_by(username=agency)).scalar_one()
u.agency_code = proj.agency_code or ""
db.session.commit()

so, sa = login(officer), login(agency)
print(f"用公告 #{ann.id}（项目「{(proj.name or '')[:22]}…」经办人={proj.officer}）\n")

# ① 状态查询：任何登录用户都能看
r = so.get(f"/api/announcements/{ann.id}/portal")
d = (r.get_json() or {}).get("data") or {}
check("① 状态接口通", r.status_code == 200 and "portal_status" in d, str(d)[:90])
check("① 官网功能已启用", d.get("enabled") is True)

# ② 未确认的公告不许挂
old_status, old_nid = ann.status, ann.portal_news_id
ann.status = "草稿"
ann.portal_news_id = 0
db.session.commit()
r = so.post(f"/api/announcements/{ann.id}/portal/publish")
check("② 没确认发布的公告不许挂官网",
      r.status_code == 400 and "尚未确认" in ((r.get_json() or {}).get("error", "")),
      (r.get_json() or {}).get("error", "")[:40])

# ③ 代理机构不许操作挂网
ann.status = "已确认"
db.session.commit()
r = sa.post(f"/api/announcements/{ann.id}/portal/publish")
check("③ 代理机构不许挂官网", r.status_code == 403, f"HTTP {r.status_code}")

# ④ 已挂过的不许重复挂
ann.portal_news_id = 99999
ann.portal_url = "https://www.njyy.com.cn/News/info/id/99999.html"
ann.portal_status = "已挂网"
db.session.commit()
r = so.post(f"/api/announcements/{ann.id}/portal/publish")
check("④ 已挂网的不许重复挂",
      r.status_code == 400 and "已挂网" in ((r.get_json() or {}).get("error", "")),
      (r.get_json() or {}).get("error", "")[:40])

# ⑤ 没挂过的不许撤
ann.portal_news_id = 0
ann.portal_url = ""
db.session.commit()
r = so.post(f"/api/announcements/{ann.id}/portal/revoke")
check("⑤ 没挂过的不许撤网", r.status_code == 400, (r.get_json() or {}).get("error", "")[:40])

# ⑥ 列表接口把挂网字段带出来
ann.portal_status, ann.portal_url, ann.portal_news_id = "已挂网", "https://x/y.html", 123
db.session.commit()
r = so.get("/api/announcements?type=procurement")
rows = [x for x in (r.get_json() or {}).get("data", []) if x["id"] == ann.id]
check("⑥ 列表带出 portal_url 供前端展示",
      bool(rows) and rows[0].get("portal_url") == "https://x/y.html",
      str(rows[0].get("portal_url") if rows else "没查到"))

# ⑦ 标题拼装与人工挂的那条一致
title = api._title_for(proj, ann)
check("⑦ 官网标题=医院全称+项目名(第X次)+公告类型",
      title.startswith("内江市第一人民医院") and title.endswith("院内竞选公告"), title[:60])

# ⑧ 正文能从公告 Word 转成 HTML
try:
    t, html, files = api._payload(app, ann.id)
    check("⑧ 正文转 HTML 成功且非空", len(html) > 200, f"{len(html)} 字符")
    check("⑧ 附件里带上了公告 Word", any(n.endswith(".docx") for n, _ in files),
          str([n for n, _ in files])[:80])
except Exception as e:                                  # noqa: BLE001
    check("⑧ 正文转 HTML", False, str(e)[:120])

# 收拾现场
ann.status, ann.portal_news_id = old_status, old_nid
ann.portal_url, ann.portal_status = "", ""
db.session.commit()

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
