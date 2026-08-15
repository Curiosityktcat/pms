"""用户管理功能验收（只打测试实例 1574 / pms.test.db，不碰正式库）。"""
import os
import sys

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"

import requests

BASE = "http://127.0.0.1:1574"
# 用「写给用户的那个测试口令」而不是临时口令：脚本会重置 admin 密码，
# 用别的值会把用户手上的口令冲掉（2026-08-15 已经害他登不进去一次）。
# 口令同步在 /home/huangxb/files/PMS测试环境访问方式_2026-08-15.md
ADMIN_PW = "0HBNkSpPJQnQOU"
ok_count, bad = 0, []


def check(tag, cond, extra=""):
    global ok_count
    if cond:
        ok_count += 1
        print(f"OK   {tag} {extra}")
    else:
        bad.append(tag)
        print(f"FAIL {tag} {extra}")


# 0. 在测试库里把 admin 密码设成已知值（正式库不受影响）
from app import create_app
from models import db
from models.user import User
from services.auth import hash_pw
import secrets

app = create_app()
with app.app_context():
    print("数据库:", app.config["SQLALCHEMY_DATABASE_URI"])
    assert "test" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库，中止"
    u = db.session.execute(db.select(User).filter_by(username="admin")).scalar_one()
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash = salt, hash_pw(ADMIN_PW, salt)
    db.session.commit()

s = requests.Session()
r = s.post(f"{BASE}/api/auth/login", json={"username": "admin", "password": ADMIN_PW}, timeout=10)
check("admin 能登录", r.status_code == 200 and r.json().get("ok"), r.text[:120])

# 1. 列表 + 筛选
r = s.get(f"{BASE}/api/admin/users", params={"size": 100}, timeout=10)
d = r.json()
check("① 账号列表", d.get("ok") and d.get("total", 0) >= 40, f"共 {d.get('total')} 个")
r = s.get(f"{BASE}/api/admin/users", params={"role": "dept", "size": 100}, timeout=10)
check("① 按角色筛选", all(u["role"] == "dept" for u in r.json().get("data", [])),
      f"dept {r.json().get('total')} 个")

# 2. 建科室账号 → 用一次性密码登录 → 只能进科室门户
r = s.post(f"{BASE}/api/admin/users", json={
    "username": "财务科", "display_name": "财务科", "role": "dept", "dept_code": "CWK"}, timeout=10)
d = r.json()
new_pw = d.get("password", "")
new_id = (d.get("user") or {}).get("id")
check("② 建科室账号", d.get("ok") and new_pw and new_id, f"密码长度 {len(new_pw)}")
s2 = requests.Session()
r = s2.post(f"{BASE}/api/auth/login", json={"username": "财务科", "password": new_pw}, timeout=10)
check("② 新账号能登录", r.status_code == 200 and r.json().get("ok"), r.text[:100])
r = s2.get(f"{BASE}/api/dept/me", timeout=10)
check("② 新账号能进科室门户", r.status_code == 200 and r.json().get("ok"), r.text[:80])
r = s2.get(f"{BASE}/api/projects", timeout=10)
check("② 新账号被闸门挡住别的模块", r.status_code == 403, f"HTTP {r.status_code}")

# 3. 建经办人账号
r = s.post(f"{BASE}/api/admin/users", json={
    "username": "测试经办人", "display_name": "测试经办人", "role": "officer"}, timeout=10)
d = r.json()
off_pw, off_id = d.get("password", ""), (d.get("user") or {}).get("id")
check("③ 建经办人账号", d.get("ok") and off_id)
s3 = requests.Session()
r = s3.post(f"{BASE}/api/auth/login", json={"username": "测试经办人", "password": off_pw}, timeout=10)
check("③ 经办人能登录", r.json().get("ok"))

# 9. 非 admin 访问后台接口 → 403
r = s3.get(f"{BASE}/api/admin/users", timeout=10)
check("⑨ 非 admin 访问被拒", r.status_code == 403, f"HTTP {r.status_code}")

# 4. 重置密码：旧失效、新可用
r = s.post(f"{BASE}/api/admin/users/{off_id}/reset-password", json={}, timeout=10)
newpw2 = r.json().get("password", "")
check("④ 重置密码返回新密码", bool(newpw2) and newpw2 != off_pw)
r = requests.post(f"{BASE}/api/auth/login", json={"username": "测试经办人", "password": off_pw}, timeout=10)
check("④ 旧密码失效", not r.json().get("ok"), r.text[:60])
r = requests.post(f"{BASE}/api/auth/login", json={"username": "测试经办人", "password": newpw2}, timeout=10)
check("④ 新密码可登录", r.json().get("ok"))

# 5. 停用 → 登录被拒
r = s.post(f"{BASE}/api/admin/users/{off_id}/toggle-active", json={}, timeout=10)
check("⑤ 停用成功", r.json().get("ok") and r.json()["user"]["active"] == 0)
r = requests.post(f"{BASE}/api/auth/login", json={"username": "测试经办人", "password": newpw2}, timeout=10)
check("⑤ 停用后登录被拒", not r.json().get("ok"), r.text[:80])

# 6. 自锁保护
admin_id = next(u["id"] for u in s.get(f"{BASE}/api/admin/users", params={"q": "admin", "size": 50},
                                       timeout=10).json()["data"] if u["username"] == "admin")
r = s.post(f"{BASE}/api/admin/users/{admin_id}/toggle-active", json={}, timeout=10)
check("⑥ 不能停用 admin 自己", r.status_code == 400, r.json().get("error", "")[:40])
r = s.put(f"{BASE}/api/admin/users/{admin_id}", json={"role": "officer"}, timeout=10)
check("⑥ 不能给 admin 降权", r.status_code == 400, r.json().get("error", "")[:40])
r = s.delete(f"{BASE}/api/admin/users/{admin_id}", timeout=10)
check("⑥ 不能删除 admin", r.status_code == 400, r.json().get("error", "")[:40])

# 7. 科室字典：新增 → 可选 → 有账号绑定则不可删
r = s.post(f"{BASE}/api/admin/depts", json={
    "code": "TESTKS", "name": "验收测试科", "category": ["需求"], "sort_no": 999}, timeout=10)
check("⑦ 新增科室", r.json().get("ok"), r.text[:80])
r = s.get(f"{BASE}/api/admin/depts", timeout=10)
codes = [x["code"] for x in r.json().get("data", [])]
check("⑦ 新科室出现在字典", "TESTKS" in codes, f"共 {len(codes)} 条")
r = s.delete(f"{BASE}/api/admin/depts/{[x['id'] for x in r.json()['data'] if x['code']=='CWK'][0]}", timeout=10)
check("⑦ 有账号绑定的科室不可删", r.status_code == 400, r.json().get("error", "")[:40])

# 8. 变更历史里没有密码
r = s.get(f"{BASE}/api/admin/users/{off_id}/audit", timeout=10)
rows = r.json().get("data", [])
blob = str(rows)
check("⑧ 有变更历史", len(rows) >= 3, f"{len(rows)} 条：{[x['action'] for x in rows]}")
check("⑧ 历史里没有密码痕迹",
      newpw2 not in blob and off_pw not in blob and "pw_hash" not in blob and "salt" not in blob)

# 收尾：删掉验收造的数据（有业务痕迹的会被拒，属预期）
for uid in (new_id, off_id):
    if uid:
        rr = s.delete(f"{BASE}/api/admin/users/{uid}", timeout=10)
        print(f"清理账号 {uid}: {rr.status_code} {rr.text[:60]}")
dl = s.get(f"{BASE}/api/admin/depts", timeout=10).json()["data"]
tid = [x["id"] for x in dl if x["code"] == "TESTKS"]
if tid:
    print("清理科室 TESTKS:", s.delete(f"{BASE}/api/admin/depts/{tid[0]}", timeout=10).status_code)

print(f"\n通过 {ok_count} 项" + (f"，失败：{bad}" if bad else "，全部通过"))
