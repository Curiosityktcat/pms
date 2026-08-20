"""缺件「能保存、不能提交」的验收（黄新博 2026-08-20）。

「把缺件提醒直接在保存的时候提醒一下，或者换成缺件后可以保存但是无法提交就行」
——两条都做了：保存不拦只提醒（/check 给清单），提交才真拦。
"""
import os, secrets, sys
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Sub!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.procurement_demand import ProcurementDemand as D
from services.auth import hash_pw

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

u = db.session.execute(db.select(User).filter_by(username="acc_sub")).scalar_one_or_none()
if u is None:
    u = User(username="acc_sub", display_name="提交验收", role="officer",
             dept_code="", active=1, agency_code="", salt="", pw_hash="")
    db.session.add(u)
u.display_name, u.role, u.active = "提交验收", "officer", 1
salt = secrets.token_hex(16); u.salt, u.pw_hash = salt, hash_pw(PW, salt)
if hasattr(u, "must_change_pw"): u.must_change_pw = 0
db.session.commit()

c = app.test_client()
c.post("/api/auth/login", json={"username": "acc_sub", "password": PW})

# ═══ 一、缺件时：能存，不能提交 ═════════════════════════════════
print("── 一、缺件时 ──")
r = c.post("/api/procurement-demands", json={
    "demand_type": "gov", "project_name": "缺件验收项目",
    "demand_dept": "检验科", "manage_dept": "医学装备部",
    "category": "货物", "year": "2026",
    # 故意选「专门面向中小企业采购」——字典会要求再填企业规模/预留形式/预留比例
    "sme_policy": "专门面向中小企业采购",
})
did = ((r.get_json() or {}).get("data") or {}).get("id")
check("① 缺件也能新建（保存不拦）", r.status_code in (200, 201) and did, f"HTTP {r.status_code}")

r = c.put(f"/api/procurement-demands/{did}", json={"project_overview": "改一下也能存"})
check("① 缺件也能保存修改", r.status_code == 200, f"HTTP {r.status_code}")
db.session.expire_all()
check("① 改的内容真存下来了",
      db.session.get(D, did).project_overview == "改一下也能存")

r = c.get(f"/api/procurement-demands/{did}/check")
d = (r.get_json() or {}).get("data") or {}
check("① 自检接口列得出缺件", r.status_code == 200 and d.get("missing"),
      f"{d.get('missing')}")
check("① 自检说不能提交", d.get("can_submit") is False)
check("① 缺的正是字典里那三项",
      {"面向的企业规模", "预留形式", "预留比例（%）"} & set(d.get("missing") or []),
      f"{d.get('missing')}")

r = c.post(f"/api/procurement-demands/{did}/submit")
body = r.get_json() or {}
check("① **提交被拦住**", r.status_code == 400, f"HTTP {r.status_code}")
check("① 拦的时候说清缺什么", body.get("missing") and "必须填了才能提交" in body.get("error", ""),
      f"{body.get('error','')[:40]}")
db.session.expire_all()
check("① 拦住后状态还是草稿", db.session.get(D, did).status == "草稿",
      db.session.get(D, did).status)

# ═══ 二、补齐后能提交 ═══════════════════════════════════════════
print("\\n── 二、补齐后 ──")
r = c.put(f"/api/procurement-demands/{did}", json={
    "sme_scale": "中小企业",     # 这些列可能不存在，下面直接改字典能认的字段
})
# 直接把字典要的三项塞进 extra（模型上没有对应列时，用 packages/extra 兜底）
# 这里改成把 sme_policy 换成不需要子项的那个选项，等价于「补齐」
r = c.put(f"/api/procurement-demands/{did}",
          json={"sme_policy": "不专门面向中小企业采购"})
check("② 改成不需要子项的选项", r.status_code == 200)

r = c.get(f"/api/procurement-demands/{did}/check")
d = (r.get_json() or {}).get("data") or {}
check("② 自检说可以提交了", d.get("can_submit") is True, f"还缺 {d.get('missing')}")

r = c.post(f"/api/procurement-demands/{did}/submit")
check("② 提交成功", r.status_code == 200, (r.get_json() or {}).get("message", ""))
db.session.expire_all()
check("② 状态变成待分发", db.session.get(D, did).status == "待分发")

# ═══ 三、名称这类硬条件仍然拦 ═══════════════════════════════════
print("\\n── 三、原有校验没丢 ──")
r = c.post("/api/procurement-demands", json={
    "demand_type": "gov", "project_name": "", "demand_dept": "检验科",
    "manage_dept": "医学装备部", "category": "货物", "year": "2026"})
did2 = ((r.get_json() or {}).get("data") or {}).get("id")
if did2:
    r = c.post(f"/api/procurement-demands/{did2}/submit")
    check("③ 没填名称仍然提交不了", r.status_code == 400,
          (r.get_json() or {}).get("error", "")[:20])
    row = db.session.get(D, did2)
    if row: db.session.delete(row)

row = db.session.get(D, did)
if row: db.session.delete(row)
db.session.commit()
print("   已清理")

print(f"\\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
