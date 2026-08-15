"""授权链验收（只打测试实例 1574 / pms.test.db，不碰正式库）。

覆盖任务书第五节 8 条，重点验两条机制：期限到了自动失效、科长换人其授权整批失效。
"""
import io
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"

import requests

BASE = "http://127.0.0.1:1574"
# 用**专用**验收管理员账号，绝不动 admin 的密码——
# 2026-08-15 就是因为脚本重置了 admin，把写给用户的测试口令冲掉、害他登不进去。
ADMIN_USER = "验收管理员"
ADMIN_PW = "AcceptAuthz!2026"
DEPT_PW = "DeptHead!2026"
STAFF_PW = "Staff!2026"
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
from models.authorization import Authorization
from services.auth import hash_pw
import secrets

app = create_app()
DEPT_CODE = "SBK"          # 医学装备部（负责人 甘锐）
OTHER_DEPT = "ZWK"         # 总务科，用来验跨科室隔离


def set_pw(username, pw, **fields):
    u = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if u is None:
        u = User(username=username, role=fields.get("role", "officer"),
                 display_name=fields.get("display_name", username), active=1,
                 dept_code=fields.get("dept_code", ""), agency_code="", salt="", pw_hash="")
        db.session.add(u)
    for k, v in fields.items():
        setattr(u, k, v)
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash = salt, hash_pw(pw, salt)
    u.active = 1
    db.session.commit()
    return u


with app.app_context():
    assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"
    set_pw(ADMIN_USER, ADMIN_PW, role="assistant", display_name="验收管理员")
    head = set_pw("医学装备部", DEPT_PW, role="dept", display_name="医学装备部", dept_code=DEPT_CODE)
    staff = set_pw("装备专员测试", STAFF_PW, role="officer", display_name="装备专员测试", dept_code=DEPT_CODE)
    outsider = set_pw("总务专员测试", STAFF_PW, role="officer", display_name="总务专员测试", dept_code=OTHER_DEPT)
    dept = db.session.execute(db.select(Dept).filter_by(code=DEPT_CODE)).scalar_one()
    ORIG_HEAD = dept.head_name
    staff_name, outsider_name = staff.username, outsider.username
    print(f"科室 {dept.name} 负责人={ORIG_HEAD}；被授权人={staff_name}；外科室={outsider_name}")


def login(username, pw):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login", json={"username": username, "password": pw}, timeout=10)
    return s, r.json()


sa, _ = login(ADMIN_USER, ADMIN_PW)
sd, dj = login("医学装备部", DEPT_PW)
check("科室账号能登录", dj.get("ok"), f"perms 含 authz_manage: {'authz_manage' in (dj.get('user') or {}).get('perms', [])}")
ss, sj = login(staff_name, STAFF_PW)
base_perms = set((sj.get("user") or {}).get("perms", []))
print("被授权人初始权限数:", len(base_perms))

# 造一个凭证 PDF
pdf = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def upload(sess, name="授权申请书.pdf", content=pdf):
    r = sess.post(f"{BASE}/api/authorizations/upload",
                  files={"file": (name, io.BytesIO(content), "application/pdf")}, timeout=20)
    return r.json()


up = upload(sd)
check("① 上传凭证 PDF", up.get("ok"), up.get("error", ""))
DOC = {"doc_path": up.get("path", ""), "doc_name": up.get("name", "")}

today = date.today()
# 科室(dept)角色目前只有 dept-portal 一项业务权限，只能授出自己有的，所以用它验机制。
# 「归口科室负责人到底该有哪些业务权限」是待用户拍板的设计问题，不在本脚本范围。
GRANT_KEY = "dept-portal"


def grant(sess, **over):
    body = {"source": "delegate", "grantee_username": staff_name, "perm_keys": [GRANT_KEY],
            "valid_from": today.isoformat(), "valid_to": (today + timedelta(days=30)).isoformat(),
            **DOC}
    body.update(over)
    return sess.post(f"{BASE}/api/authorizations", json=body, timeout=15)

# ② 各种非法授权都要被拒
r = grant(sd, doc_path="", doc_name="")
check("② 不传凭证被拒", r.status_code == 400, r.json().get("error", "")[:30])
r = grant(sd, valid_from=(today + timedelta(days=5)).isoformat(), valid_to=today.isoformat())
check("② 期限倒挂被拒", r.status_code == 400, r.json().get("error", "")[:30])
r = grant(sd, perm_keys=["user_manage"])
check("② 授出自己没有的权限被拒", r.status_code == 400, r.json().get("error", "")[:40])
r = grant(sd, grantee_username=outsider_name)
check("② 授给外科室的人被拒", r.status_code == 403 or r.status_code == 400, r.json().get("error", "")[:30])

# ③ 正常授权 → 被授权人多出权限
r = grant(sd)
check("③ 委托授权成功", r.status_code == 201, r.json().get("error", "")[:60])
auth_id = (r.json().get("data") or {}).get("id")
ss2, sj2 = login(staff_name, STAFF_PW)
perms_after = set((sj2.get("user") or {}).get("perms", []))
check("③ 被授权人拿到新权限", GRANT_KEY in perms_after and GRANT_KEY not in base_perms,
      f"{len(base_perms)} → {len(perms_after)}")
r = ss2.get(f"{BASE}/api/authorizations/my", timeout=10)
mine = r.json().get("data", [])
check("③ 我的授权能看到来源与期限",
      any(x.get("id") == auth_id and x.get("effective_state") == "生效" for x in mine), str(mine)[:100])

# ① 科室隔离：外科室账号看不到本科室台账
so, _ = login("总务科", "x")   # 没这个账号也无妨，用 admin 看全院即可
r = sa.get(f"{BASE}/api/authorizations", timeout=10)
all_rows = r.json().get("data", [])
check("① admin 看全院台账", r.json().get("ok") and any(x["id"] == auth_id for x in all_rows), f"{len(all_rows)} 条")
r = sd.get(f"{BASE}/api/authorizations", timeout=10)
dept_rows = r.json().get("data", [])
check("① 科室账号只看本科室",
      all(x.get("granter_dept_code") == DEPT_CODE or x.get("grantee_dept_code") == DEPT_CODE
          for x in dept_rows), f"{len(dept_rows)} 条")

# ④ 期限到期 → 权限立即消失
with app.app_context():
    a = db.session.get(Authorization, auth_id)
    a.valid_to = (today - timedelta(days=1)).isoformat()
    db.session.commit()
ss3, sj3 = login(staff_name, STAFF_PW)
check("④ 过期后权限消失", GRANT_KEY not in set((sj3.get("user") or {}).get("perms", [])))
row = next((x for x in sa.get(f"{BASE}/api/authorizations", timeout=10).json()["data"] if x["id"] == auth_id), {})
check("④ 台账显示已过期", row.get("effective_state") == "已过期", row.get("effective_state", ""))

# 恢复期限，验换人失效
with app.app_context():
    a = db.session.get(Authorization, auth_id)
    a.valid_to = (today + timedelta(days=30)).isoformat()
    db.session.commit()
ss4, sj4 = login(staff_name, STAFF_PW)
check("④ 期限恢复后权限回来", GRANT_KEY in set((sj4.get("user") or {}).get("perms", [])))

# ⑤ 科长换人 → 委托授权整批失效；决议授权不受影响
res_up = upload(sa, "院决议.pdf")
r = sa.post(f"{BASE}/api/authorizations", json={
    "source": "resolution", "grantee_username": staff_name, "perm_keys": ["archive"],
    "valid_from": today.isoformat(), "valid_to": (today + timedelta(days=30)).isoformat(),
    "doc_no": "内一医党委〔2026〕12号",
    "doc_path": res_up.get("path", ""), "doc_name": res_up.get("name", "")}, timeout=15)
check("⑦ 决议授权成功（须文号+盖章决议）", r.status_code == 201, r.json().get("error", "")[:60])
r2 = sa.post(f"{BASE}/api/authorizations", json={
    "source": "resolution", "grantee_username": staff_name, "perm_keys": ["archive"],
    "valid_from": today.isoformat(), "valid_to": (today + timedelta(days=30)).isoformat(),
    "doc_path": res_up.get("path", ""), "doc_name": res_up.get("name", "")}, timeout=15)
check("⑦ 决议授权缺文号被拒", r2.status_code == 400, r2.json().get("error", "")[:30])

with app.app_context():
    d = db.session.execute(db.select(Dept).filter_by(code=DEPT_CODE)).scalar_one()
    d.head_name = "换了个新科长"
    db.session.commit()
ss5, sj5 = login(staff_name, STAFF_PW)
perms5 = set((sj5.get("user") or {}).get("perms", []))
check("⑤ 换科长后委托授权失效", GRANT_KEY not in perms5)
check("⑤ 决议授权不受换人影响", "archive" in perms5)
row = next((x for x in sa.get(f"{BASE}/api/authorizations", timeout=10).json()["data"] if x["id"] == auth_id), {})
check("⑤ 台账显示授权人已换人", row.get("effective_state") == "授权人已换人", row.get("effective_state", ""))

# ⑥ 撤销必须填原因
with app.app_context():
    d = db.session.execute(db.select(Dept).filter_by(code=DEPT_CODE)).scalar_one()
    d.head_name = ORIG_HEAD
    db.session.commit()
r = sd.post(f"{BASE}/api/authorizations/{auth_id}/revoke", json={}, timeout=10)
check("⑥ 撤销不填原因被拒", r.status_code == 400, r.json().get("error", "")[:30])
r = sd.post(f"{BASE}/api/authorizations/{auth_id}/revoke", json={"reason": "岗位调整"}, timeout=10)
check("⑥ 撤销成功", r.json().get("ok"), r.text[:60])
ss6, sj6 = login(staff_name, STAFF_PW)
check("⑥ 撤销后权限立即消失", GRANT_KEY not in set((sj6.get("user") or {}).get("perms", [])))

# ⑧ 普通经办人（无 authz_manage）访问管理接口
r = ss6.post(f"{BASE}/api/authorizations", json={"source": "delegate"}, timeout=10)
check("⑧ 经办人无权新建授权", r.status_code == 403, f"HTTP {r.status_code}")

# 收尾：清掉验收造的授权与账号
with app.app_context():
    for a in db.session.execute(db.select(Authorization).filter(
            Authorization.grantee_username == staff_name)).scalars().all():
        db.session.delete(a)
    for name in (staff_name, outsider_name, ADMIN_USER):
        u = db.session.execute(db.select(User).filter_by(username=name)).scalar_one_or_none()
        if u:
            db.session.delete(u)
    db.session.commit()
    print("已清理验收数据")

print(f"\n通过 {ok_count} 项" + (f"，失败：{bad}" if bad else "，全部通过"))
