"""看板上所有日期必须是 YYYY-MM-DD（任务书硬约束⑤）。

之前时间线上混着「2026年6月24日」和「2026-06-24」两种写法。
"""
import os, sys, re, secrets
sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
os.environ["PMS_CAPTCHA_ON"] = "0"
PW = "Monitor!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from services.auth import hash_pw

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"
u = db.session.execute(db.select(User).filter_by(username="acc_leader")).scalar_one()
salt = secrets.token_hex(16); u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
db.session.commit()
c = app.test_client()
c.post("/api/auth/login", json={"username": "acc_leader", "password": PW})

ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
bad_list, bad_tl = [], []
seen_rows = seen_nodes = 0

page = 1
while True:
    r = c.get("/api/project-monitor/projects",
              query_string={"page": page, "page_size": 100, "archived": "1"})
    body = r.get_json() or {}
    rows = body.get("data") or []
    if not rows:
        break
    for row in rows:
        seen_rows += 1
        for k in ("updated_at", "last_action_at"):
            v = row.get(k) or ""
            if v and not ISO.match(v):
                bad_list.append((row["id"], k, v))
        t = c.get(f"/api/project-monitor/projects/{row['id']}/timeline")
        for rd in ((t.get_json() or {}).get("data") or {}).get("rounds") or []:
            for n in rd.get("nodes") or []:
                seen_nodes += 1
                v = n.get("at") or ""
                if v and not ISO.match(v):
                    bad_tl.append((row["id"], n.get("label"), v))
    if page * 100 >= (body.get("total") or 0):
        break
    page += 1

check("① 列表日期全是 YYYY-MM-DD", not bad_list, f"扫了 {seen_rows} 行，异常 {bad_list[:5]}")
check("② 时间线日期全是 YYYY-MM-DD", not bad_tl, f"扫了 {seen_nodes} 个节点，异常 {bad_tl[:5]}")

r = c.get("/api/project-monitor/plans")
check("③ 计划页签只对科室开放", r.status_code == 403, f"HTTP {r.status_code}")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
