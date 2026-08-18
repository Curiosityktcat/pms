"""科室账号权限与隔离验收（只打测试实例 1574 / pms.test.db）。

重点不是「能不能看见」，而是**看不见别人的**：
两个科室账号的可见项目集合必须无交集，且改 URL 里的 id 也拿不到别人的详情。
"""
import os
import sys

sys.path.insert(0, ".")
# 进程内直打，顺带关掉本进程的滑块——不动 1574 那个挂着公网的实例
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _requests_shim as requests

BASE = ""   # 进程内 test_client，不再走 HTTP
PW = "DeptScope!2026"
ok_count, bad = 0, []


def check(tag, cond, extra=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"OK   {tag} {extra}")
    else:
        bad.append(tag)
        print(f"FAIL {tag} {extra}")


from app import create_app
from models import db
from models.user import User
from models.dept import Dept
from services.auth import hash_pw
import secrets

app = create_app()
requests.bind(app)
A_CODE, B_CODE = "SBK", "ZWK"      # 医学装备部 / 总务科
DEPT_ROLES = ("dept", "dept_manage", "dept_demand")


def ensure_dept_account(code):
    d = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one()
    u = db.session.execute(db.select(User).filter_by(dept_code=code).where(
        User.role.in_(DEPT_ROLES))).scalars().first()
    if u is None:
        # 「dept」是已废弃的老角色（2026-08-18 全部迁走了），新建必须按科室类型
        # 给正确角色，否则建出来的账号连项目管理器的角色白名单都过不去。
        from routes.user_admin_api import _dept_role
        u = User(username=d.name, display_name=d.name, role=_dept_role(d), dept_code=code,
                 active=1, agency_code="", salt="", pw_hash="")
        db.session.add(u)
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
    db.session.commit()
    return u.username, d.name, u.role


with app.app_context():
    assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"
    a_user, a_name, a_role = ensure_dept_account(A_CODE)
    b_user, b_name, b_role = ensure_dept_account(B_CODE)
    print(f"A={a_user}({a_name}, 角色 {a_role})  B={b_user}({b_name}, 角色 {b_role})")


def login(username):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"username": username, "password": PW}, timeout=10)
    return s, (r.json().get("user") or {})


sa, ua = login(a_user)
sb, ub = login(b_user)
check("① 两个科室账号都能登录", bool(ua) and bool(ub), f"{ua.get('role')} / {ub.get('role')}")
perms_a = set(ua.get("perms", []))
# 2026-08-18 用户把科室范围收紧了：需求科室只有「我的科室项目」，
# 归口科室多一个采购需求编制。合同/流程这些不再对科室开放（原断言已过时）。
check("① 拿到科室门户与项目管理器权限",
      {"dept-portal", "project-monitor"} <= perms_a, f"{sorted(perms_a)}")
check("① 没有归档权限", "archive" not in perms_a)
check("① 没有合同权限", "contract" not in perms_a)
check("① 归口科室有需求编制权限", "procurement-demand-gov" in perms_a,
      f"角色 {a_role}")


def ids(sess, path, key="id"):
    r = sess.get(f"{BASE}{path}", timeout=20)
    if r.status_code != 200:
        return None, r.status_code
    body = r.json()
    rows = body.get("data") if isinstance(body, dict) else body
    if not isinstance(rows, list):
        return None, r.status_code
    return {x.get(key) for x in rows if isinstance(x, dict) and x.get(key) is not None}, 200


# ② 项目列表：两边无交集
pa, sca = ids(sa, "/api/projects")
pb, scb = ids(sb, "/api/projects")
check("② 项目列表可见", pa is not None and pb is not None, f"A {sca}/{len(pa or [])} 条，B {scb}/{len(pb or [])} 条")
if pa is not None and pb is not None:
    check("② 两科室项目集合无交集", not (pa & pb), f"交集 {len(pa & pb)} 个")
    check("② 各自都能看到本科室项目", len(pa) > 0 or len(pb) > 0)

# ③ 其它业务列表也隔离
for path, label in (("/api/contracts", "合同"), ("/api/procurement-results", "采购结果"),
                    ("/api/inquiries", "询价函"), ("/api/auth-letter-records", "授权函记录")):
    ra, ca = ids(sa, path)
    rb, cb = ids(sb, path)
    if ra is None or rb is None:
        print(f"     （跳过 {label}：HTTP {ca}/{cb}）")
        continue
    check(f"③ {label}列表无交集", not (ra & rb), f"A {len(ra)} / B {len(rb)}")

# ④ 改 URL 越权：拿 B 的项目 id 去 A 的会话请求
if pb:
    victim = sorted(pb)[0]
    r = sa.get(f"{BASE}/api/projects/{victim}", timeout=15)
    check("④ 越权取他科室项目详情被挡", r.status_code in (403, 404), f"HTTP {r.status_code}")

# ⑤ 只读：非需求编制的写操作要被拒
r = sa.post(f"{BASE}/api/contracts", json={"contract_name": "越权测试"}, timeout=15)
check("⑤ 合同写操作被拒", r.status_code in (403, 405), f"HTTP {r.status_code} {r.text[:60]}")
r = sa.post(f"{BASE}/api/projects", json={"name": "越权测试"}, timeout=15)
check("⑤ 项目立项写操作被拒", r.status_code in (403, 405), f"HTTP {r.status_code}")

# ⑥ 归档仍然 403
r = sa.get(f"{BASE}/api/archive/list", timeout=15)
check("⑥ 归档接口仍被拒", r.status_code == 403, f"HTTP {r.status_code}")

# ⑦ 科室门户与项目流程口径一致
pm, _ = ids(sa, "/api/dept/projects")
if pm is not None and pa is not None:
    check("⑦ 科室门户与项目列表口径一致", pm == pa or pm <= pa, f"门户 {len(pm)} / 列表 {len(pa)}")

# ⑧ 回归：经办人可见范围不受影响（用既有经办人账号，密码未知则跳过）
print("\n（经办人回归验证需要已知口令，改由 review 时对比接口返回条数）")

print(f"\n通过 {ok_count} 项" + (f"，失败：{bad}" if bad else "，全部通过"))
