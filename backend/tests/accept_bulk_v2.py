"""批量建号新规则的验收（只打测试库）。

黄新博 2026-08-19：账号名同科室名；显示名用「科室名-负责人」；
重名要能自动让开（「审计科」被监督岗占过）；一次性密码必须强制首改。
"""
import os, sys, secrets
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
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

# 清掉所有科室账号，好把批量建号完整验一遍
n = 0
for u in db.session.execute(db.select(User).where(User.role.in_(DEPT_ROLES))).scalars().all():
    db.session.delete(u); n += 1
db.session.commit()
print(f"清掉 {n} 个科室账号，重新批量建\n")

# 故意造一个占名的账号：科室叫「检验科」，先让一个非科室账号占住这个名
clash_dept = db.session.execute(db.select(Dept).filter_by(active=1, name="检验科")).scalar_one_or_none()
if clash_dept is None:
    clash_dept = db.session.execute(db.select(Dept).filter_by(active=1)).scalars().first()
squatter = db.session.execute(db.select(User).filter_by(username=clash_dept.name)).scalar_one_or_none()
if squatter is None:
    squatter = User(username=clash_dept.name, display_name=clash_dept.name,
                    role="supervisor", dept_code="", active=1, agency_code="",
                    salt="x", pw_hash="x")
    db.session.add(squatter); db.session.commit()
print(f"占名账号：{squatter.username!r}（角色 {squatter.role}），科室「{clash_dept.name}」建号时应自动让开\n")

c = app.test_client()
with c.session_transaction() as sess:
    sess["user"] = "admin"; sess["role"] = "admin"
    sess["display_name"] = "系统管理员"; sess["dept_code"] = ""

# ── 预览 ──────────────────────────────────────────────────────
r = c.post("/api/admin/users/bulk-dept-accounts", json={"dry_run": True})
d = r.get_json() or {}
pending = d.get("pending") or []
check("① 预览能跑", r.status_code == 200 and len(pending) > 0, f"{len(pending)} 个")
before = db.session.execute(db.select(db.func.count()).select_from(User)).scalar_one()

sample = pending[0]
check("① 预览里带了显示名与负责人",
      "display_name" in sample and "head_name" in sample, f"{sample}")

clash_row = next((x for x in pending if x["dept_code"] == clash_dept.code), None)
check("① 撞名的科室在预览里就让开了",
      clash_row is not None and clash_row["username"] != clash_dept.name,
      f"{clash_row and clash_row['username']!r}")

# ── 真建 ──────────────────────────────────────────────────────
r = c.post("/api/admin/users/bulk-dept-accounts", json={})
d = r.get_json() or {}
created = d.get("created") or []
check("② 批量建号成功", r.status_code == 200 and len(created) == len(pending),
      f"建了 {len(created)}，预览说 {len(pending)}")

after = db.session.execute(db.select(db.func.count()).select_from(User)).scalar_one()
check("② 账号数对得上", after - before == len(created), f"{before} → {after}")

# 显示名 = 科室名-负责人
depts = {d_.code: d_ for d_ in db.session.execute(
    db.select(Dept).filter_by(active=1)).scalars()}
wrong = []
for x in created:
    dp = depts.get(x["dept_code"])
    if dp is None:
        continue
    head = (dp.head_name or "").strip()
    want = f"{dp.name}-{head}" if head else dp.name
    if x["display_name"] != want:
        wrong.append((x["display_name"], want))
check("② 显示名都是「科室名-负责人」", not wrong, f"不符 {wrong[:3]}")

check("② 每个都发了一次性密码",
      all(len(x.get("password") or "") >= 8 for x in created),
      f"最短 {min(len(x.get('password') or '') for x in created)} 位")
check("② 密码各不相同",
      len({x["password"] for x in created}) == len(created))

# 强制首改密
rows = db.session.execute(db.select(User).where(
    User.username.in_([x["username"] for x in created]))).scalars().all()
check("② 全部强制首次改密",
      all(getattr(u, "must_change_pw", 0) == 1 for u in rows),
      f"{sum(1 for u in rows if getattr(u,'must_change_pw',0)==1)}/{len(rows)}")

# 撞名的那个
made = next((x for x in created if x["dept_code"] == clash_dept.code), None)
check("② 撞名科室真建出来了且名字让开",
      made is not None and made["username"] != clash_dept.name,
      f"{made and made['username']!r}")
check("② 占名的老账号没被动",
      db.session.execute(db.select(User).filter_by(username=clash_dept.name)
                         ).scalar_one().role == "supervisor")

# 角色分配
by_role = {}
for x in created:
    by_role[x["role"]] = by_role.get(x["role"], 0) + 1
check("② 角色按科室类型分", set(by_role) <= {"dept_manage", "dept_demand"}, f"{by_role}")
mism = []
for x in created:
    dp = depts.get(x["dept_code"])
    if dp is None: continue
    want = "dept_manage" if (dp.dept_type or "") == "行后" and dp.code != "CGB" else "dept_demand"
    if x["role"] != want:
        mism.append((dp.name, x["role"], want))
check("② 每个科室的角色都对", not mism, f"不符 {mism[:3]}")

# ── 建出来的号真能用吗 ────────────────────────────────────────
one = next(x for x in created if x["role"] == "dept_demand")
c2 = app.test_client()
r = c2.post("/api/auth/login", json={"username": one["username"], "password": one["password"]})
info = (r.get_json() or {}).get("user") or {}
check("③ 新账号能登录", r.status_code == 200 and bool(info),
      f"{one['username']} / {one['display_name']}")
perms = set(info.get("perms") or [])
check("③ 需求科室能进采购需求编制", "procurement-demand-gov" in perms)
check("③ 需求科室没有采购计划池", "procurement-plan" not in perms)
check("③ 登录返回里带着「科室名-负责人」",
      "-" in (info.get("display_name") or "") or not (depts.get(one["dept_code"]).head_name or "").strip(),
      f"{info.get('display_name')!r}")

# 先把一次性密码改掉，否则测到的是强制改密闸门而不是权限
PW1 = "Njyy!2026#a1"
r = c2.post("/api/auth/chpwd", json={"old": one["password"], "n1": PW1, "n2": PW1})
check("③ 改掉一次性密码", r.status_code == 200, (r.get_json() or {}).get("error", ""))

r = c2.get("/api/procurement-demands")
check("③ 新账号真能打开采购需求编制", r.status_code == 200, f"HTTP {r.status_code}")
r = c2.get("/api/procurement-plans")
check("③ 需求科室进不了计划池", r.status_code == 403, f"HTTP {r.status_code}")

two = next(x for x in created if x["role"] == "dept_manage")
c3 = app.test_client()
c3.post("/api/auth/login", json={"username": two["username"], "password": two["password"]})
PW2 = "Njyy!2026#a2"
c3.post("/api/auth/chpwd", json={"old": two["password"], "n1": PW2, "n2": PW2})
r = c3.get("/api/procurement-plans")
check("③ 归口科室能进计划池", r.status_code == 200, f"{two['username']} HTTP {r.status_code}")

# ── 强制首次改密：一次性密码必须用一次就作废 ──────────────────
print()
three = next(x for x in created if x["role"] == "dept_demand"
             and x["username"] not in (one["username"], two["username"]))
c4 = app.test_client()
r = c4.post("/api/auth/login", json={"username": three["username"], "password": three["password"]})
info = (r.get_json() or {}).get("user") or {}
check("④ 登录返回里标了要改密", info.get("must_change_pw") == 1, f"{info.get('must_change_pw')}")

r = c4.get("/api/procurement-demands")
check("④ 没改密之前业务接口被挡", r.status_code == 403
      and (r.get_json() or {}).get("must_change_pw") is True,
      f"HTTP {r.status_code}")
r = c4.get("/api/auth/me")
check("④ 但 /me 仍然放行（前端要靠它弹框）", r.status_code == 200)

# 新旧一样、太短都要拦
r = c4.post("/api/auth/chpwd", json={"old": three["password"],
                                     "n1": three["password"], "n2": three["password"]})
check("④ 新密码不能和原密码相同", r.status_code == 400,
      (r.get_json() or {}).get("error", "")[:24])
r = c4.post("/api/auth/chpwd", json={"old": three["password"], "n1": "abc123", "n2": "abc123"})
check("④ 新密码太短被拦", r.status_code == 400, (r.get_json() or {}).get("error", "")[:20])

NEWPW = "Njyy!2026#ok"
r = c4.post("/api/auth/chpwd", json={"old": three["password"], "n1": NEWPW, "n2": NEWPW})
check("④ 改密成功", r.status_code == 200, (r.get_json() or {}).get("message", ""))

r = c4.get("/api/procurement-demands")
check("④ 改完立刻放行，不用重新登录", r.status_code == 200, f"HTTP {r.status_code}")

db.session.expire_all()
u3 = db.session.execute(db.select(User).filter_by(username=three["username"])).scalar_one()
check("④ 库里的标记已清", getattr(u3, "must_change_pw", 1) == 0)

c5 = app.test_client()
r = c5.post("/api/auth/login", json={"username": three["username"], "password": three["password"]})
check("④ 一次性密码已失效", r.status_code == 401, f"HTTP {r.status_code}")
r = c5.post("/api/auth/login", json={"username": three["username"], "password": NEWPW})
check("④ 新密码能登录", r.status_code == 200)
check("④ 重新登录后不再要求改密",
      ((r.get_json() or {}).get("user") or {}).get("must_change_pw") == 0)

# ── 重复执行不重复建 ──────────────────────────────────────────
r = c.post("/api/admin/users/bulk-dept-accounts", json={})
check("④ 再跑一次不重复建号", len((r.get_json() or {}).get("created") or []) == 0,
      f"第二次建了 {len((r.get_json() or {}).get('created') or [])} 个")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
