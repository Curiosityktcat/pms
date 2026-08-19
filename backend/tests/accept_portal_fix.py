"""黄新博 2026-08-19 用「麻醉手术中心」实测报的四个问题（只打测试库）。

  ① 在线人数显示 0（接口被闸门挡了，前端还静默吞错）
  ② 公告首页登录后看不到公告，没登录反而能看
  ③ 采购部公告和相关文件看不到
  ④ 代理机构考核不该给科室看；工具栏对科室只开放法规库和投诉质疑数据库
    （④ 是纯前端配置，这里验后端接口该挡的还挡着）
"""
import os, sys, secrets
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Portal!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.dept import Dept
from services.auth import hash_pw

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

DEPT_ROLES = ("dept", "dept_manage", "dept_demand")


def dept_acct(prefer=None):
    q = db.select(User).where(User.role.in_(DEPT_ROLES), User.active == 1)
    u = None
    if prefer:
        u = db.session.execute(q.where(User.username == prefer)).scalars().first()
    if u is None:
        u = db.session.execute(q).scalars().first()
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash = salt, hash_pw(PW, salt)
    if hasattr(u, "must_change_pw"): u.must_change_pw = 0
    db.session.commit()
    return u


u = dept_acct("麻醉手术中心")
c = app.test_client()
r = c.post("/api/auth/login", json={"username": u.username, "password": PW})
info = (r.get_json() or {}).get("user") or {}
print(f"用科室账号 {u.username}（{info.get('role')}）\n")
check("登录成功", r.status_code == 200 and bool(info))

# ═══ ① 在线人数 ═════════════════════════════════════════════════
r = c.get("/api/presence/ping")
d = (r.get_json() or {}).get("data") or {}
check("① 科室账号能上报在线", r.status_code == 200, f"HTTP {r.status_code}")
check("① 在线人数至少是自己这 1 个", d.get("count", 0) >= 1, f"count={d.get('count')}")

c2 = app.test_client()
u2 = db.session.execute(db.select(User).filter_by(role="officer", active=1)).scalars().first()
salt = secrets.token_hex(16); u2.salt, u2.pw_hash = salt, hash_pw(PW, salt)
if hasattr(u2, "must_change_pw"): u2.must_change_pw = 0
db.session.commit()
c2.post("/api/auth/login", json={"username": u2.username, "password": PW})
c2.get("/api/presence/ping")
n2 = ((c.get("/api/presence/ping").get_json() or {}).get("data") or {}).get("count", 0)
check("① 两个人在线就数到 2", n2 >= 2, f"count={n2}")

# ═══ ② 公告首页 ═════════════════════════════════════════════════
anon = app.test_client()
r_anon = anon.get("/api/announcements/public")
n_anon = len((r_anon.get_json() or {}).get("data") or [])
r_in = c.get("/api/announcements/public")
n_in = len((r_in.get_json() or {}).get("data") or [])
check("② 没登录能看公开公告", r_anon.status_code == 200, f"HTTP {r_anon.status_code}，{n_anon} 条")
check("② 登录后一样能看", r_in.status_code == 200, f"HTTP {r_in.status_code}，{n_in} 条")
check("② 登录前后条数一致（公开公告与身份无关）", n_anon == n_in, f"{n_anon} vs {n_in}")

# 但「挂网管理」那个业务模块，科室仍然不该进
r = c.get("/api/announcements")
check("② 挂网管理模块对科室仍然关着", r.status_code == 403, f"HTTP {r.status_code}")

# ═══ ③ 采购部公告 ═══════════════════════════════════════════════
r = c.get("/api/dept-announcements")
check("③ 科室能看采购部公告栏", r.status_code == 200, f"HTTP {r.status_code}")
body = r.get_json() or {}
check("③ 返回结构正常", isinstance(body.get("data"), list),
      f"{len(body.get('data') or [])} 条")
# 看是所有人，发还是采购部的事——59 个科室账号进来后这条必须收紧
check("③ 科室只能看、不能往公告栏发", body.get("can_upload") is False,
      f"can_upload={body.get('can_upload')}")
r = c.post("/api/dept-announcements", json={"title": "越权测试"})
check("③ 科室发公告被拒", r.status_code in (400, 403), f"HTTP {r.status_code}")

r2 = c2.get("/api/dept-announcements")
check("③ 采购部经办人仍然能发",
      ((r2.get_json() or {}).get("can_upload")) is True,
      f"can_upload={(r2.get_json() or {}).get('can_upload')}")

# ═══ ④ 科室不该碰的还挡着 ═══════════════════════════════════════
for path, name in (("/api/agency-assessment", "代理机构考核"),
                   ("/api/contracts", "合同"),
                   ("/api/archive", "归档"),
                   ("/api/distributions", "项目分发")):
    r = c.get(path)
    check(f"④ {name}对科室仍然关着", r.status_code in (403, 404), f"HTTP {r.status_code}")

# 该给的还在
for path, name in (("/api/procurement-demands", "采购需求编制"),
                   ("/api/project-monitor/projects", "项目管理器"),
                   ("/api/dept/me", "我的科室项目")):
    r = c.get(path)
    check(f"④ {name}对科室开着", r.status_code == 200, f"HTTP {r.status_code}")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
