"""Agent 对话验收（黄新博 2026-08-20：做成像微信一样）。

重点：消息存得下、传的文件后面还记得、建议挂在那条回复上、采纳有痕迹。
不调真模型——把 llm_client.chat 换成假的，验的是我们这层的逻辑。
"""
import io as _io, json, os, secrets, sys
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Chat!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.procurement_demand import ProcurementDemand as D
from models.demand_chat import DemandChatMessage as M
from services.auth import hash_pw
from services import llm_client

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

u = db.session.execute(db.select(User).filter_by(username="acc_chat")).scalar_one_or_none()
if u is None:
    u = User(username="acc_chat", display_name="对话验收", role="officer",
             dept_code="", active=1, agency_code="", salt="", pw_hash="")
    db.session.add(u)
u.display_name, u.role, u.active = "对话验收", "officer", 1
salt = secrets.token_hex(16); u.salt, u.pw_hash = salt, hash_pw(PW, salt)
if hasattr(u, "must_change_pw"): u.must_change_pw = 0
d = D(demand_type="gov", status="草稿", created_by="对话验收",
      project_name="对话验收项目", demand_dept="检验科", manage_dept="医学装备部",
      category="货物", year="2026")
db.session.add(d); db.session.commit()
did = d.id

c = app.test_client()
c.post("/api/auth/login", json={"username": "acc_chat", "password": PW})

# 记下每次喂给模型的提示词，好验「上下文带没带」
seen = []
REPLY = ('读完了。\n{"fields": {"项目概况": {"value": "买监护仪", "evidence": "拟采购监护仪"}},'
         ' "packages": [{"技术要求": {"value": "12 导联", "evidence": "支持 12 导联"}}]}')
orig = llm_client.chat
def fake(system, user, **kw):
    seen.append(user)
    return REPLY
llm_client.chat = fake

try:
    # ═══ 一、发消息 ═══════════════════════════════════════════
    print("── 一、发消息 ──")
    r = c.get(f"/api/procurement-demands/{did}/chat")
    check("① 一开始没有消息", (r.get_json() or {}).get("data") == [])

    MAT = "心电监护仪采购需求。拟采购监护仪一批，支持 12 导联。整机质保3年。"
    r = c.post(f"/api/procurement-demands/{did}/chat",
               data={"text": "你先读一下", "file": (_io.BytesIO(MAT.encode()), "需求.txt")},
               content_type="multipart/form-data")
    dd = (r.get_json() or {}).get("data") or {}
    check("① 发得出去", r.status_code == 200 and dd.get("user") and dd.get("agent"))
    um, am = dd["user"], dd["agent"]
    check("① 我的消息记下了文字", um["text"] == "你先读一下")
    check("① 我的消息记下了附件", len(um["files"]) == 1 and um["files"][0]["name"] == "需求.txt",
          f"{um['files']}")
    check("① 它的回复分出了「话」和「建议」",
          am["text"].startswith("读完了") and am["suggestions"], f"{am['text'][:20]!r}")
    check("① 建议里有字段和包",
          "项目概况" in (am["suggestions"]["fields"] or {})
          and len(am["suggestions"]["packages"]) == 1)
    check("① 资料真的喂给了模型", "12 导联" in seen[-1], "")

    # ═══ 二、上下文 ═══════════════════════════════════════════
    print("\\n── 二、上下文 ──")
    r = c.post(f"/api/procurement-demands/{did}/chat",
               data={"text": "质保期是多久？"}, content_type="multipart/form-data")
    check("② 第二轮也能发", r.status_code == 200)
    prompt = seen[-1]
    check("② 上一轮的对话带上了", "你先读一下" in prompt)
    check("② **上一轮传的资料也带上了**（不然它会失忆）",
          "整机质保3年" in prompt, "这是对话式最关键的一条")
    check("② 它自己上一轮说的话也带上了", "读完了" in prompt)

    # ═══ 三、采纳 ═════════════════════════════════════════════
    print("\\n── 三、采纳 ──")
    mid = am["id"]
    r = c.post(f"/api/procurement-demands/{did}/chat/{mid}/apply",
               json={"fields": {"项目概况": "买监护仪"},
                     "packages": [{"技术要求": "12 导联"}]})
    d3 = r.get_json() or {}
    check("③ 采纳成功", r.status_code == 200, d3.get("message", ""))
    db.session.expire_all()
    row = db.session.get(D, did)
    check("③ 写进需求了", row.project_overview == "买监护仪")
    check("③ 包里的也写了", "12 导联" in (row.packages_json or ""))
    msg = db.session.get(M, mid)
    check("③ 采纳痕迹记在那条消息上",
          "项目概况" in json.loads(msg.applied_json or "[]"), f"{msg.applied_json}")

    r = c.get(f"/api/procurement-demands/{did}/chat")
    msgs = (r.get_json() or {}).get("data") or []
    check("③ 历史里看得到采纳标记",
          any(m.get("applied") for m in msgs), f"{[m.get('applied') for m in msgs]}")
    check("③ 历史条数对", len(msgs) == 4, f"{len(msgs)} 条")

    # ═══ 四、边界 ═════════════════════════════════════════════
    print("\\n── 四、边界 ──")
    r = c.post(f"/api/procurement-demands/{did}/chat", data={},
               content_type="multipart/form-data")
    check("④ 空消息被拦", r.status_code == 400, (r.get_json() or {}).get("error", "")[:16])

    r = c.post(f"/api/procurement-demands/{did}/chat",
               data={"text": "传个不支持的", "file": (_io.BytesIO(b"x"), "a.exe")},
               content_type="multipart/form-data")
    fs = (((r.get_json() or {}).get("data") or {}).get("user") or {}).get("files") or []
    check("④ 不支持的格式会说明", any(f.get("error") for f in fs), f"{fs}")

    # 模型挂了也要留一条，别让人以为发失败了
    llm_client.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("模型超时"))
    r = c.post(f"/api/procurement-demands/{did}/chat",
               data={"text": "模型挂了会怎样"}, content_type="multipart/form-data")
    am2 = ((r.get_json() or {}).get("data") or {}).get("agent") or {}
    check("④ 模型挂了也回一条，不是没反应",
          r.status_code == 200 and "出错" in (am2.get("text") or ""), f"{am2.get('text','')[:30]}")

    # 已立项不许改
    llm_client.chat = fake
    row.status = "已立项"; db.session.commit()
    r = c.post(f"/api/procurement-demands/{did}/chat/{mid}/apply", json={"fields": {"项目概况": "x"}})
    check("④ 已立项的需求采纳被拒", r.status_code == 400, (r.get_json() or {}).get("error", "")[:16])
finally:
    llm_client.chat = orig

db.session.execute(db.delete(M).where(M.demand_id == did))
row = db.session.get(D, did)
if row: db.session.delete(row)
db.session.commit()
print("   已清理")

print(f"\\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
