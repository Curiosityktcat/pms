"""合同审核与 rd-web 推送身份的验收（只打测试库 pms.test.db）。

对着用户 2026-08-18 报的三个 bug：
  ① 不同经办人推送时都变成黄新博的 rd-web 账号
  ② 代理机构一提交就显示「审核完成」并直接推 rd-web，经办人没审
  ③ 合同名称缺前缀，应为 合同类型名 + 项目名称 + 包号
"""
import os, sys, secrets
sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
os.environ["PMS_CAPTCHA_ON"] = "0"
PW = "Ctr!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.project import Project
from models.contract import Contract
from models.contract_attachment import ContractAttachment
from models.project_distribution import RdwebAccount
from services.auth import hash_pw
from routes.utils import get_rdweb_creds, RdwebNoAccount
from services.rdweb_contract_name import guess_contract_type, compose_name

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"


def acct(username, display, role):
    u = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if u is None:
        u = User(username=username, display_name=display, role=role,
                 dept_code="", active=1, agency_code="", salt="", pw_hash="")
        db.session.add(u)
    u.display_name, u.role, u.active = display, role, 1
    salt = secrets.token_hex(16); u.salt, u.pw_hash = salt, hash_pw(PW, salt)
    if hasattr(u, "must_change_pw"): u.must_change_pw = 0
    db.session.commit()
    return username


def login(un):
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": un, "password": PW})
    return c, ((r.get_json() or {}).get("user") or {})


# ═══ ① 不许冒名 ═══════════════════════════════════════════════════
print("── ① 推送身份不许冒名 ──")
try:
    creds = get_rdweb_creds("这个人根本没有rd-web账号")
    check("① 没配账号的人取凭据必须报错", False, f"竟然返回了 {creds[0]}")
except RdwebNoAccount as e:
    check("① 没配账号的人取凭据必须报错", True, f"报错：{str(e)[:40]}…")

try:
    creds = get_rdweb_creds("四川三盈招标代理有限公司")
    check("① 代理机构取凭据必须报错", False, f"竟然返回了 {creds[0]}")
except RdwebNoAccount:
    check("① 代理机构取凭据必须报错", True)

rows = db.session.execute(db.select(RdwebAccount).filter_by(usage="执行")).scalars().all()
if rows:
    r0 = rows[0]
    got = get_rdweb_creds(r0.owner)
    check("① 配了账号的人取到的是本人的号", got[0] == r0.phone,
          f"{r0.owner} → {got[0][:3]}****{got[0][-2:]}")
    others = [r for r in rows if r.owner != r0.owner]
    if others:
        g2 = get_rdweb_creds(others[0].owner)
        check("① 两个人取到的是不同的号", g2[0] != got[0],
              f"{r0.owner} vs {others[0].owner}")

# ═══ ③ 合同名称 ═══════════════════════════════════════════════════
print("\n── ③ 合同名称 = 类型 + 项目 + 包号 ──")
check("③ 坑爹文件名只取词根",
      guess_contract_type("内江市第一人民医院服务合同_NJYYJX-SY-2607010（第二次）-蓉旭阳.docx") == "服务合同",
      f"→ {guess_contract_type('内江市第一人民医院服务合同_NJYYJX-SY-2607010（第二次）-蓉旭阳.docx')!r}")
check("③ 带 (2)(2)(1)(1) 的也认得出",
      guess_contract_type("1.医用耗材购销协议(2)(2)(1)(1).doc") == "医用耗材购销协议")
check("③ 中选通知书不算合同类型", guess_contract_type("【中选通知书】.pdf") == "")
n = compose_name("服务合同", "2026年PNKD项目", "1")
check("③ 拼出来三段齐全", n == "服务合同-2026年PNKD项目　包1", n)
n2 = compose_name("医用耗材购销协议", "2026年标本杯项目", "2")
check("③ 包号跟着走", n2.endswith("　包2"), n2)

# ═══ ② 代理提交不许直接变审核完成、不许推送 ═══════════════════════
print("\n── ② 代理提交只到「待审核」，经办人审完才推 ──")
proj = db.session.execute(db.select(Project).where(
    Project.officer.isnot(None), Project.officer != "",
    db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))).scalars().first()
officer_name = proj.officer

ag = acct("acc_agency2", "四川三盈招标代理有限公司", "agency")
off = acct("acc_officer2", officer_name, "officer")
u = db.session.execute(db.select(User).filter_by(username=ag)).scalar_one()
u.agency_code = getattr(proj, "agency_code", "") or ""
db.session.commit()

c = Contract(project_id=proj.id, contract_number="TEST-HT-001",
             contract_name="测试合同", package_no="3", status="合同草案",
             created_by="验收", created_at="2026-08-18T00:00:00")
db.session.add(c); db.session.commit()
cid = c.id
db.session.add(ContractAttachment(contract_id=cid, original_name="1.医用耗材购销协议.doc",
                                  saved_name="x.doc", mime_type="application/msword"))
db.session.commit()
print(f"   造了合同 #{cid}（项目「{proj.name[:24]}…」经办人={officer_name}，包号=3）")

sa, ua = login(ag)
r = sa.post(f"/api/contracts/{cid}/submit", json={})
body = r.get_json() or {}
db.session.expire_all()
c = db.session.get(Contract, cid)
check("② 代理提交后状态是「待审核」", c.status == "待审核", f"实际 {c.status!r}")
check("② 代理提交的返回里没有推送动作", "rdweb_push" not in body, f"{list(body)}")
check("② 代理提交后没有 rd-web 流水号", not (c.rdweb_serial_no or ""), f"{c.rdweb_serial_no!r}")

r = sa.post(f"/api/contracts/{cid}/review", json={"contract_type": "医用耗材购销协议"})
check("② 代理不能自己审核自己", r.status_code == 403, f"HTTP {r.status_code}")

so, uo = login(off)
r = so.get(f"/api/contracts/{cid}/review-preview")
d = (r.get_json() or {}).get("data") or {}
check("② 审核弹窗能取到", r.status_code == 200, f"HTTP {r.status_code}")
check("② 弹窗猜出了合同类型", d.get("contract_type") == "医用耗材购销协议", f"{d.get('contract_type')!r}")
check("② 弹窗标明这是猜的", d.get("contract_type_guessed") is True)
check("② 弹窗预览的名称三段齐全",
      d.get("composed_name", "").startswith("医用耗材购销协议-") and d.get("composed_name", "").endswith("　包3"),
      d.get("composed_name"))
check("② 给了常用类型下拉", len(d.get("common_types") or []) >= 5, f"{len(d.get('common_types') or [])} 项")

# 审核时不填类型且库里也没有 → 必须拦住（先清掉猜测落库的可能）
r = so.post(f"/api/contracts/{cid}/review", json={"contract_type": "医用耗材购销协议"})
body = r.get_json() or {}
db.session.expire_all()
c = db.session.get(Contract, cid)
check("② 经办人审核通过后状态才是「审核完成」", c.status == "审核完成", f"实际 {c.status!r}")
check("② 记下了是谁审的", (c.reviewed_by or "") == officer_name, f"{c.reviewed_by!r}")
check("② 记下了审核时间", bool(c.reviewed_at))
check("② 审核通过才触发推送", "rdweb_push" in body, f"{list(body)}")
check("② 合同类型落库了", c.contract_type == "医用耗材购销协议", f"{c.contract_type!r}")

# 重复审核要挡
r = so.post(f"/api/contracts/{cid}/review", json={})
check("② 不能重复审核", r.status_code == 400, f"HTTP {r.status_code}")

# 清理
db.session.execute(db.delete(ContractAttachment).where(ContractAttachment.contract_id == cid))
db.session.delete(db.session.get(Contract, cid))
db.session.commit()
print(f"   已清理测试合同 #{cid}")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
