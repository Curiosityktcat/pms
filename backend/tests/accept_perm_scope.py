"""三档科室权限范围的验收（用户 2026-08-18 原话）：

  需求科室只能看 0. 我的科室项目，其余不给权限。
  归口管理科室在需求科室的基础之上增加采购需求编制。
  监督在归口基础之上可以看开标管理和授权书。
"""
import os, sys, secrets
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Scope!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.dept import Dept
from models.role_permission import RolePermission as RP
from services.auth import hash_pw
from services.permission import DEPT_DEMAND_PERMS, DEPT_MANAGE_PERMS, SUPERVISOR_PERMS

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

DEMAND_SET = set(DEPT_DEMAND_PERMS)
MANAGE_SET = set(DEPT_MANAGE_PERMS)
SUPER_SET = set(SUPERVISOR_PERMS)
DEMAND_KEYS = {"procurement-demand-gov", "internal-bid-demand", "procurement-demand-sole",
               "procurement-demand-inquiry", "procurement-demand-emergency"}

# ── 角色范围本身 ───────────────────────────────────────────────────
print("── 三档范围 ──")
check("① 需求科室只有「我的科室项目」+ 项目管理器",
      DEMAND_SET == {"dept-portal", "project-monitor"}, f"{sorted(DEMAND_SET)}")
check("① 归口 = 需求 + 采购需求编制",
      MANAGE_SET == DEMAND_SET | DEMAND_KEYS, f"多出 {sorted(MANAGE_SET - DEMAND_SET)}")
check("① 监督 = 归口 + 开标管理 + 授权函",
      SUPER_SET == MANAGE_SET | {"bid", "auth-letter"}, f"多出 {sorted(SUPER_SET - MANAGE_SET)}")
for name, ks in (("需求科室", DEMAND_SET), ("归口科室", MANAGE_SET), ("监督", SUPER_SET)):
    check(f"① {name}没有归档权限", "archive" not in ks)
    check(f"① {name}没有合同/结果确认权限", not ({"contract", "procurement-result"} & ks))
check("① 需求科室没有采购需求编制", not (DEMAND_SET & DEMAND_KEYS))

# ── 库里真的落到位了吗 ─────────────────────────────────────────────
print("\n── 库里的权限表 ──")
for role, want in (("dept_demand", DEMAND_SET), ("dept_manage", MANAGE_SET),
                   ("supervisor", SUPER_SET)):
    got = {r for r in db.session.execute(
        db.select(RP.perm_key).filter_by(role=role)).scalars()}
    check(f"② {role} 落库正确", got == want, f"多 {sorted(got-want)} 少 {sorted(want-got)}")

n_old = db.session.execute(db.select(db.func.count()).select_from(User)
                           .where(User.role == "dept")).scalar_one()
check("② 没有账号还挂在老 dept 角色上", n_old == 0, f"还剩 {n_old} 个")

# ── 真账号登录看到什么 ─────────────────────────────────────────────
print("\n── 真账号实测 ──")


def pick(role):
    return db.session.execute(db.select(User).filter_by(role=role, active=1)).scalars().first()


def login_as(u):
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash = salt, hash_pw(PW, salt)
    if hasattr(u, "must_change_pw"): u.must_change_pw = 0
    db.session.commit()
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": u.username, "password": PW})
    return c, ((r.get_json() or {}).get("user") or {})


for role, want, label in (("dept_demand", DEMAND_SET, "需求科室"),
                          ("dept_manage", MANAGE_SET, "归口科室"),
                          ("supervisor", SUPER_SET, "监督")):
    u = pick(role)
    if u is None:
        check(f"③ 有 {label} 账号可测", False, "库里没有这个角色的账号"); continue
    c, info = login_as(u)
    perms = set(info.get("perms") or [])
    # authz_manage 是运行时补的（科室负责人要能做委托授权），不算超范围
    extra = perms - want - {"authz_manage"}
    check(f"③ {label}（{u.username}）登录后权限不超范围", not extra, f"多出 {sorted(extra)}")
    check(f"③ {label} 能进「我的科室项目」", "dept-portal" in perms)
    # 实打实打几个不该进的接口
    for path, name in (("/api/archive/list", "归档"), ("/api/contracts", "合同"),
                       ("/api/procurement-results", "采购结果")):
        r = c.get(path)
        check(f"③ {label} 进不了{name}", r.status_code in (401, 403), f"HTTP {r.status_code}")
    if role == "dept_demand":
        r = c.get("/api/procurement-demands")
        check("③ 需求科室进不了采购需求编制", r.status_code in (401, 403), f"HTTP {r.status_code}")
    else:
        r = c.get("/api/procurement-demands")
        check(f"③ {label} 能进采购需求编制", r.status_code == 200, f"HTTP {r.status_code}")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
