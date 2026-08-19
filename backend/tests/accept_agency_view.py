"""代理机构对「代理机构考核」的可见性与只读（只打测试库）。

黄新博 2026-08-19 补充：「代理机构可以看到自己的考核得分，而不能够进行操作」。
所以要同时验两头：**看得到自己的**，以及**改不动、也看不到别家的**。
"""
import os, sys, secrets
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Agc!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.project import Project
from models.agency_assessment import AgencyAssessment
from services.auth import hash_pw

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"


def login_as(u):
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
    if hasattr(u, "must_change_pw"): u.must_change_pw = 0
    db.session.commit()
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": u.username, "password": PW})
    return c, ((r.get_json() or {}).get("user") or {})


# 挑一个真的有考核记录的代理机构
rows = db.session.execute(db.select(AgencyAssessment)).scalars().all()
codes = {r.agency_code for r in rows if r.agency_code}
print(f"库里考核记录 {len(rows)} 条，涉及 {len(codes)} 家代理机构")

ag = None
for code in sorted(codes):
    ag = db.session.execute(db.select(User).filter_by(role="agency", agency_code=code)
                            ).scalars().first()
    if ag:
        break
if ag is None:
    ag = db.session.execute(db.select(User).filter_by(role="agency")).scalars().first()
print(f"用代理账号：{ag.username}（agency_code={ag.agency_code}）\n")

c, info = login_as(ag)
check("① 代理机构能登录", bool(info), f"角色 {info.get('role')}")

# ── 看得到自己的 ──────────────────────────────────────────────
r = c.get("/api/agency-assessments")
body = r.get_json() or {}
mine = body.get("data") or []
check("② 能打开考核列表", r.status_code == 200, f"HTTP {r.status_code}，{len(mine)} 条")
alien = [x for x in mine if x.get("agency_code") and x["agency_code"] != ag.agency_code]
check("② 列表里只有自己家的", not alien, f"混入 {len(alien)} 条")

r = c.get("/api/agency-assessments/summary")
check("② 能看自己的汇总得分", r.status_code == 200, f"HTTP {r.status_code}")
s_body = (r.get_json() or {}).get("data")
if isinstance(s_body, list):
    alien2 = [x for x in s_body if x.get("agency_code") and x["agency_code"] != ag.agency_code]
    check("② 汇总里也只有自己家的", not alien2, f"混入 {len(alien2)} 家")

# 自己家、且考核**已提交定稿**的项目——代理看不到还在打分的草稿，这是有意为之
submitted = db.session.execute(db.select(AgencyAssessment).filter_by(
    agency_code=ag.agency_code, status="已提交")).scalars().first()
own = db.session.get(Project, submitted.project_id) if submitted else None
if own:
    r = c.get(f"/api/agency-assessments/project/{own.id}")
    d = (r.get_json() or {}).get("data") or {}
    check("② 能看自己已定稿的考核详情", r.status_code == 200, f"HTTP {r.status_code}")
    check("② 详情标了只读", d.get("readonly") is True, f"readonly={d.get('readonly')}")
    check("② 看得到分数", d.get("total_score") is not None, f"得分={d.get('total_score')}")
else:
    check("② 找得到已定稿的考核可测", False, "这家代理没有已提交的考核")

# 草稿状态的看不到（还在打分，不该让被考核方看见）
draft = db.session.execute(db.select(AgencyAssessment).filter_by(
    agency_code=ag.agency_code, status="草稿")).scalars().first()
if draft:
    r = c.get(f"/api/agency-assessments/project/{draft.project_id}")
    check("② 还在打分的草稿代理看不到", r.status_code == 404,
          f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:22]}")

# ── 改不动 ────────────────────────────────────────────────────
if own:
    r = c.post(f"/api/agency-assessments/project/{own.id}", json={"items": []})
    check("③ 代理不能给自己打分", r.status_code == 403,
          f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:24]}")
row = rows[0] if rows else None
if row:
    r = c.post(f"/api/agency-assessments/{row.id}/revoke", json={})
    check("③ 代理不能撤销考核", r.status_code == 403, f"HTTP {r.status_code}")

# ── 看不到别家的 ──────────────────────────────────────────────
other = db.session.execute(db.select(Project).where(
    Project.agency_code.isnot(None), Project.agency_code != "",
    Project.agency_code != ag.agency_code)).scalars().first()
if other:
    r = c.get(f"/api/agency-assessments/project/{other.id}")
    # 404 而不是 403：项目可见性在更前面就挡住了，连「这个项目存在」都不告诉他，
    # 比 403 更严实
    check("④ 看不到别家代理的考核", r.status_code in (403, 404),
          f"HTTP {r.status_code}（项目 {other.id} 属于 {other.agency_code}）")
    check("④ 挡的时候不泄露别家信息",
          (other.name or "") not in str(r.get_json() or {}),
          f"{str(r.get_json() or {})[:50]}")

# ── 科室/监督仍然一点都看不到 ────────────────────────────────
dept = db.session.execute(db.select(User).where(
    User.role.in_(("dept", "dept_manage", "dept_demand")), User.active == 1)).scalars().first()
cd, _ = login_as(dept)
r = cd.get("/api/agency-assessments")
check("⑤ 科室仍然进不去考核", r.status_code == 403, f"HTTP {r.status_code}")

# ── 采购部照旧能打分 ──────────────────────────────────────────
off = db.session.execute(db.select(User).filter_by(role="assistant", active=1)).scalars().first()
co, _ = login_as(off)
r = co.get("/api/agency-assessments")
check("⑥ 采购部能看全部", r.status_code == 200,
      f"HTTP {r.status_code}，{len((r.get_json() or {}).get('data') or [])} 条")
r = co.get("/api/agency-assessments/meta")
check("⑥ 采购部标着可打分", ((r.get_json() or {}).get("data") or {}).get("can_assess") is True,
      f"can_assess={((r.get_json() or {}).get('data') or {}).get('can_assess')}")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
