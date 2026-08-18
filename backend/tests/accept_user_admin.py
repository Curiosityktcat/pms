"""用户管理功能验收（只打测试实例 1574 / pms.test.db，不碰正式库）。"""
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
requests.bind(app)
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
r = s.get(f"{BASE}/api/admin/users", params={"role": "dept_manage", "size": 100}, timeout=10)
check("① 按角色筛选", all(u["role"] == "dept_manage" for u in r.json().get("data", [])),
      f"dept_manage {r.json().get('total')} 个")

# 上一轮如果中途挂了，验收账号会留在库里，导致这一轮「建号」直接撞重名而失败。
# 脚本必须能反复跑，所以先把自己留下的痕迹清掉。
# 列表接口有每页上限，一次 size=1000 只会拿到第一页，遗留账号可能在后面几页，
# 所以必须翻页找完（上一轮踩过：没找到 → 建号撞重名 → 后面一串连锁失败）。
_all, _page = [], 1
while True:
    _d = s.get(f"{BASE}/api/admin/users", params={"page": _page, "size": 100}, timeout=20).json()
    _rows = _d.get("data") or []
    _all += _rows
    if not _rows or len(_all) >= (_d.get("total") or 0):
        break
    _page += 1
# 上一轮如果中途挂了，验收账号会留在库里，下一轮建号就撞重名，
# 然后后面一长串检查跟着连锁失败。先把自己留下的痕迹清干净。
for _u in _all:
    if _u.get("username") in ("测试经办人", "财务科"):
        _r = s.delete(f"{BASE}/api/admin/users/{_u['id']}", timeout=10)
        print(f"清掉上一轮遗留的验收账号 {_u['username']}: {_r.status_code}")

# 验收科室的编码每次都换一个：删不掉的情况是有的（比如被停用而不是真删），
# 固定编码会让下一轮直接撞「科室编码已存在」。
import random as _rnd
# 科室编码只允许大写字母，不能带数字
_TESTKS = "TK" + "".join(_rnd.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(4))

# 建号验收不再写死「财务科/CWK」——那个科室在正式的全院名单里根本不存在
# （早年测试自己造的）。改成从真实科室里挑一个**还没有账号**的来建，
# 这样脚本在任何一份库副本上都跑得通。
_depts = s.get(f"{BASE}/api/admin/depts", timeout=20).json().get("data") or []
_used = {u.get("dept_code") for u in _all
         if u.get("role") in ("dept", "dept_manage", "dept_demand")}
_target = next((d for d in _depts
                if d.get("active") and d.get("code") and d["code"] not in _used), None)
if _target is None:
    # 全都有账号了：借用其中一个，先把它的账号删掉再建，保持脚本可反复跑
    _target = next(d for d in _depts if d.get("active"))
    for _u in _all:
        if _u.get("dept_code") == _target["code"]:
            s.delete(f"{BASE}/api/admin/users/{_u['id']}", timeout=10)
_CODE = _target["code"]
_NAME = _target["name"]
_ROLE = "dept_manage" if _target.get("is_manage_dept") else "dept_demand"
print(f"建号验收用科室：{_NAME}({_CODE})，应使用角色 {_ROLE}")

# 2. 建科室账号 → 用一次性密码登录 → 只能进科室门户
r = s.post(f"{BASE}/api/admin/users", json={
    "username": _NAME, "display_name": _NAME, "role": _ROLE, "dept_code": _CODE}, timeout=10)
d = r.json()
new_pw = d.get("password", "")
new_id = (d.get("user") or {}).get("id")
check("② 建科室账号", d.get("ok") and new_pw and new_id, f"密码长度 {len(new_pw)}")
s2 = requests.Session()
r = s2.post(f"{BASE}/api/auth/login", json={"username": _NAME, "password": new_pw}, timeout=10)
check("② 新账号能登录", r.status_code == 200 and r.json().get("ok"), r.text[:100])
r = s2.get(f"{BASE}/api/dept/me", timeout=10)
check("② 新账号能进科室门户", r.status_code == 200 and r.json().get("ok"), r.text[:80])
# /api/projects 对科室是**开放但按科室收口**的（科室门户和项目管理器都要用它，
# 看到的只有本科室的），所以拿它验闸门验不出东西。改用科室确实进不去的合同模块。
r = s2.get(f"{BASE}/api/contracts", timeout=10)
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
    "code": _TESTKS, "name": f"验收测试科{_TESTKS}", "category": ["需求"], "sort_no": 999}, timeout=10)
check("⑦ 新增科室", r.json().get("ok"), r.text[:80])
r = s.get(f"{BASE}/api/admin/depts", timeout=10)
codes = [x["code"] for x in r.json().get("data", [])]
check("⑦ 新科室出现在字典", _TESTKS in codes, f"共 {len(codes)} 条")
_bound = [x["id"] for x in r.json()["data"] if x["code"] == _CODE]
r = s.delete(f"{BASE}/api/admin/depts/{_bound[0]}", timeout=10)
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
tid = [x["id"] for x in dl if x["code"] == _TESTKS]
if tid:
    print(f"清理科室 {_TESTKS}:", s.delete(f"{BASE}/api/admin/depts/{tid[0]}", timeout=10).status_code)

print(f"\n通过 {ok_count} 项" + (f"，失败：{bad}" if bad else "，全部通过"))
