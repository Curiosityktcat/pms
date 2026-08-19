"""采购需求 Agent 验收（黄新博 2026-08-19 ⑩ 第 2 条）。

重点不是「它能不能填」，而是 **它会不会编**、**会不会绕过规则**：
  · 原文没有的必须留空，不能推断补全
  · 每条建议必须带原文依据，给不出依据的一律丢掉
  · 字典锁定的字段，连建议都不能给，硬塞也写不进去
  · 只提建议不落库，人点了采纳才写
"""
import io as _io, json, os, secrets, sys
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Agt!2026"
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
from services import demand_agent

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

# ═══ 一、白名单与依据的过滤（不调模型，直接验规则）═══════════════
print("── 一、过滤规则 ──")
raw = {
    "fields": {
        "项目概况": {"value": "买监护仪", "evidence": "拟采购监护仪一批"},
        "合同支付约定": {"value": "先付一半", "evidence": ""},          # 没依据
        "预算金额": {"value": "100000", "evidence": "预算十万"},        # 不在白名单
        "采购组织形式": {"value": "自行采购", "evidence": "自行采购"},   # 被锁定
        "履约验收时间": {"value": "", "evidence": "有"},                # 空值
    },
    "packages": [{"技术要求": {"value": "12 导联", "evidence": "支持 12 导联"},
                  "预算金额": {"value": "9", "evidence": "九"}}],
    "notes": ["测试"],
}
import types
orig_chat = None
from services import llm_client
def fake_chat(system, user, **kw):
    return json.dumps(raw, ensure_ascii=False)
orig_chat, llm_client.chat = llm_client.chat, fake_chat
try:
    out = demand_agent.suggest("随便什么资料", locked_names=["采购组织形式"])
finally:
    llm_client.chat = orig_chat

f = out["fields"]
check("① 有依据的留下", "项目概况" in f, f"{list(f)}")
check("① 没依据的丢掉", "合同支付约定" not in f)
check("① 白名单外的丢掉（预算金额这类不让它碰）", "预算金额" not in f)
check("① 字典锁定的连建议都不给", "采购组织形式" not in f)
check("① 空值不算建议", "履约验收时间" not in f)
check("① 丢掉的会说明原因", any("没给原文依据" in n or "不在可填范围" in n
                                for n in out["notes"]), f"{out['notes'][:2]}")
pk = out["packages"][0]
check("① 包里也只留白名单字段", "技术要求" in pk and "预算金额" not in pk, f"{list(pk)}")

# 模型返回垃圾时要报人话
llm_client.chat = lambda system, user, **kw: "对不起我不知道"
try:
    demand_agent.suggest("x")
    check("① 模型返回垃圾时报错", False, "居然没报错")
except RuntimeError as e:
    check("① 模型返回垃圾时报人话", "重试" in str(e) or "解析" in str(e), str(e)[:40])
finally:
    llm_client.chat = orig_chat

# ═══ 二、接口：建议不落库，采纳才写 ═════════════════════════════
print("\\n── 二、接口 ──")
u = db.session.execute(db.select(User).filter_by(username="acc_agt")).scalar_one_or_none()
if u is None:
    u = User(username="acc_agt", display_name="Agent验收", role="officer",
             dept_code="", active=1, agency_code="", salt="", pw_hash="")
    db.session.add(u)
u.display_name, u.role, u.active = "Agent验收", "officer", 1
salt = secrets.token_hex(16); u.salt, u.pw_hash = salt, hash_pw(PW, salt)
if hasattr(u, "must_change_pw"): u.must_change_pw = 0
d = D(demand_type="gov", status="草稿", created_by="Agent验收",
      project_name="Agent验收项目", demand_dept="检验科", manage_dept="医学装备部",
      category="货物", year="2026")
db.session.add(d); db.session.commit()
did = d.id

c = app.test_client()
c.post("/api/auth/login", json={"username": "acc_agt", "password": PW})

llm_client.chat = fake_chat
try:
    r = c.post(f"/api/procurement-demands/{did}/agent/suggest",
               data={"text": "拟采购监护仪一批，支持 12 导联。"},
               content_type="multipart/form-data")
finally:
    llm_client.chat = orig_chat
dd = (r.get_json() or {}).get("data") or {}
check("② 粘文字也能出建议", r.status_code == 200 and dd.get("fields"), f"HTTP {r.status_code}")
db.session.expire_all()
check("② 出建议不落库", not (db.session.get(D, did).project_overview or ""),
      f"{db.session.get(D, did).project_overview!r}")

r = c.post(f"/api/procurement-demands/{did}/agent/suggest",
           data={}, content_type="multipart/form-data")
check("② 什么都不给会提示", r.status_code == 400, (r.get_json() or {}).get("error", "")[:20])

# 采纳
r = c.post(f"/api/procurement-demands/{did}/agent/apply",
           json={"fields": {"项目概况": "买监护仪"},
                 "packages": [{"技术要求": "12 导联"}]})
d2 = r.get_json() or {}
check("③ 采纳后写进去了", r.status_code == 200, d2.get("message", ""))
db.session.expire_all()
row = db.session.get(D, did)
check("③ 字段落库了", row.project_overview == "买监护仪", f"{row.project_overview!r}")
check("③ 包里的也落库了", "12 导联" in (row.packages_json or ""), f"{(row.packages_json or '')[:40]}")

# 硬塞锁定字段和白名单外字段
r = c.post(f"/api/procurement-demands/{did}/agent/apply",
           json={"fields": {"采购组织形式": "自行采购", "预算金额": "999",
                            "项目概况": "改了"}})
d3 = r.get_json() or {}
check("④ 硬塞锁定字段写不进去",
      any("锁定" in x for x in d3.get("skipped") or []), f"{d3.get('skipped')}")
check("④ 硬塞白名单外的写不进去",
      any("不在可写范围" in x for x in d3.get("skipped") or []))
db.session.expire_all()
check("④ 允许的那条还是写进去了", db.session.get(D, did).project_overview == "改了")

db.session.delete(db.session.get(D, did)); db.session.commit()
print("   已清理")

print(f"\\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
