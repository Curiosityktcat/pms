"""C2 补充验收：经办人回归 + 批量建科室账号（只打测试实例 1574）。"""
import os
import sys

sys.path.insert(0, ".")
# 进程内直打，顺带关掉本进程的滑块——不动 1574 那个挂着公网的实例
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"

import sys as _sys, os as _os
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
import _requests_shim as requests
import secrets

BASE = ""   # 进程内 test_client，不再走 HTTP
ADMIN_PW = "0HBNkSpPJQnQOU"      # 与写给用户的口令一致，跑完不改变
OFF_PW = "OfficerReg!2026"
ok, bad = 0, []


def check(tag, cond, extra=""):
    global ok
    if cond:
        ok += 1
        print(f"OK   {tag} {extra}")
    else:
        bad.append(tag)
        print(f"FAIL {tag} {extra}")


from app import create_app
from models import db
from models.user import User
from models.dept import Dept
from services.auth import hash_pw

app = create_app()
requests.bind(app)
with app.app_context():
    assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"
    # 回归要用「真的负责着项目的经办人」才有意义：新账号本来就没有项目，看到 0 是对的。
    real_officer = db.session.execute(db.text(
        "SELECT officer, COUNT(*) c FROM projects WHERE IFNULL(officer,'')<>'' "
        "GROUP BY officer ORDER BY c DESC LIMIT 1")).first()
    OFFICER_NAME, OFFICER_PROJECTS = real_officer[0], real_officer[1]
    u = db.session.execute(db.select(User).filter_by(username="回归经办人")).scalar_one_or_none()
    if u is None:
        u = User(username="回归经办人", display_name="回归经办人", role="officer",
                 active=1, dept_code="", agency_code="", salt="", pw_hash="")
        db.session.add(u)
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash, u.active, u.role = salt, hash_pw(OFF_PW, salt), 1, "officer"
    u.display_name = OFFICER_NAME   # 项目按经办人姓名归属
    db.session.commit()
    total_projects = db.session.execute(db.select(db.func.count()).select_from(
        db.select(db.text("id")).select_from(db.text("projects")).subquery())).scalar_one()
    dept_total = db.session.execute(db.select(db.func.count()).select_from(Dept).filter_by(active=1)).scalar_one()
    # 只数**启用**科室：停用科室（院办/预保科/资产管理组）名下还挂着老账号，
    # 把它们算进覆盖数会让 missing 少算，甚至算出负数。
    active_codes = {r[0] for r in db.session.execute(
        db.select(Dept.code).filter_by(active=1)).all() if r[0]}
    have_acct = {r[0] for r in db.session.execute(db.select(User.dept_code).where(
        User.role.in_(("dept", "dept_manage", "dept_demand")))).all()
        if r[0] and r[0] in active_codes}
    missing = len(active_codes) - len(have_acct)
    print(f"库里项目 {total_projects} 个；启用科室 {len(active_codes)} 个，其中 {missing} 个没有账号")
    print(f"回归用经办人：{OFFICER_NAME}，名下 {OFFICER_PROJECTS} 个项目")
    # 把上一轮批量建的账号清掉，好把「批量建号」再完整验一遍
    from models.user_audit_log import UserAuditLog
    codes_with_dept = db.session.execute(db.select(User).where(
        User.role.in_(("dept_manage", "dept_demand")))).scalars().all()
    removed = 0
    for acc in codes_with_dept:
        if acc.username not in ("医学装备部", "总务科") and acc.id > 41:
            db.session.delete(acc); removed += 1
    db.session.commit()
    print("清掉上一轮批量建的账号:", removed)
    have_acct = {r[0] for r in db.session.execute(db.select(User.dept_code).where(
        User.role.in_(("dept", "dept_manage", "dept_demand")))).all()
        if r[0] and r[0] in active_codes}
    missing = len(active_codes) - len(have_acct)

so = requests.Session()
so.post(f"{BASE}/api/auth/login", json={"username": "回归经办人", "password": OFF_PW}, timeout=10)
r = so.get(f"{BASE}/api/projects", timeout=30)
rows = (r.json() or {}).get("data", [])
check("⑨ 经办人可见范围不受影响", len(rows) > 0,
      f"经办人 {OFFICER_NAME} 看到 {len(rows)} 个（其名下 {OFFICER_PROJECTS} 个）")
r = so.get(f"{BASE}/api/archive/projects", timeout=20)
check("⑨ 经办人归档接口不被拦", r.status_code != 403, f"HTTP {r.status_code}")

sa = requests.Session()
sa.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, timeout=10)
r = sa.post(f"{BASE}/api/admin/users/bulk-dept-accounts", json={"dry_run": True}, timeout=60)
d = r.json()
preview = d.get("pending") or []
check("④ 批量建号 dry_run 预览", d.get("ok") and len(preview) == missing,
      f"预览 {len(preview)} 个，应为 {missing}")
r = sa.post(f"{BASE}/api/admin/users/bulk-dept-accounts", json={}, timeout=180)
d2 = r.json()
created = d2.get("created") or []
check("④ 批量建号执行", d2.get("ok") and len(created) == missing, f"建了 {len(created)} 个")
if created:
    one = created[0]
    name, pw = one.get("username"), one.get("password")
    check("④ 返回的密码能登录", bool(pw) and requests.post(
        f"{BASE}/api/auth/login", json={"username": name, "password": pw}, timeout=10
    ).json().get("ok"), f"{name}")
    roles = {c.get("role") for c in created}
    check("④ 新账号角色按科室类型区分", roles <= {"dept_manage", "dept_demand"} and len(roles) == 2, str(roles))
r = sa.post(f"{BASE}/api/admin/users/bulk-dept-accounts", json={}, timeout=60)
again = r.json().get("created") or []
check("④ 重复执行不重复建号", len(again) == 0, f"第二次建了 {len(again)} 个")

with app.app_context():
    n = db.session.execute(db.select(db.func.count()).select_from(User).where(
        User.role.in_(("dept", "dept_manage", "dept_demand")))).scalar_one()
    print("现有科室账号总数:", n)

print(f"\n通过 {ok} 项" + (f"，失败：{bad}" if bad else "，全部通过"))
