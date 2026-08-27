"""验收：① 采购公告轮次自动跟随项目轮次（第六次不再选不到/印错）
        ② 合同环节强控：中标通知书前置 + 归档必须齐盖章件与三个日期
只打测试库 pms.test.db。
"""
import os, sys, secrets, io
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
from models.package import Package
from models.procurement_doc_attachment import ProcurementDocAttachment
from services.auth import hash_pw

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

def acct(username, display, role, agency_code=""):
    u = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if u is None:
        u = User(username=username, display_name=display, role=role,
                 dept_code="", active=1, agency_code=agency_code, salt="", pw_hash="")
        db.session.add(u)
    u.display_name, u.role, u.active, u.agency_code = display, role, 1, agency_code
    salt = secrets.token_hex(16); u.salt, u.pw_hash = salt, hash_pw(PW, salt)
    if hasattr(u, "must_change_pw"): u.must_change_pw = 0
    db.session.commit()
    return username

def login(un):
    c = app.test_client()
    c.post("/api/auth/login", json={"username": un, "password": PW})
    return c

# ═══ ① 轮次 ═══════════════════════════════════════════════════════
print("── ① 采购公告轮次跟着项目走 ──")
from services.announcement import _round_cn, get_filename, ROUND_CN
check("① 第六次的中文数字是「六」", _round_cn(6) == "六", f"→{_round_cn(6)!r}")
check("① 第十次是「十」", _round_cn(10) == "十", f"→{_round_cn(10)!r}")
check("① 超出表退回阿拉伯数字", _round_cn(12) == "12", f"→{_round_cn(12)!r}")

class _FakeAnn:  round_number = 6
class _FakeProj: number = "NJYYJX-SY-2606999"
fn = get_filename(_FakeProj(), _FakeAnn())
check("① 公告文件名带「（第六次）」而不是第五次", "（第六次）" in fn, f"→{fn}")

src = io.open("services/procurement_result_word.py", encoding="utf-8").read()
check("① 结果确认表 ROUND_CN 已扩到十", '"六", "七", "八", "九", "十"' in src)

# 找个走公告流程的项目，把轮次拨到 6，验证后端不听前端传的轮次
from routes.announcement_api import ANNOUNCEMENT_REQUIRED_METHODS
proj = db.session.execute(db.select(Project).where(
    Project.method.in_(ANNOUNCEMENT_REQUIRED_METHODS),
    Project.agency_code != "",
    db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
    db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
)).scalars().first()
if proj is None:
    print("   (测试库里没有可编公告的项目，跳过接口级验证)")
else:
    old_round, old_conf, old_off = proj.round, proj.doc_confirmed, proj.officer
    proj.round, proj.doc_confirmed = 6, 1
    if not proj.officer:
        proj.officer = "验收经办人"
    db.session.commit()
    off = acct("acc_off_round", proj.officer, "officer")
    so = login(off)
    # 清掉上次验收可能残留的第 6 次公告，否则「每轮只能发一次」会挡住
    from models.announcement import Announcement as _A
    for _old in db.session.execute(db.select(_A).filter_by(
            project_id=proj.id, ann_type="procurement", round_number=6)).scalars().all():
        db.session.delete(_old)
    db.session.commit()
    r = so.get("/api/announcements/projects")
    rows = [x for x in (r.get_json() or {}).get("data", []) if x["id"] == proj.id]
    check("① 下拉给出的 round 就是项目当前轮次 6", bool(rows) and rows[0].get("round") == 6,
          f"→{rows[0].get('round') if rows else '项目不在可选列表'}")
    # 前端就算传个 3 过来，也要落成 6
    r = so.post("/api/announcements", json={"project_id": proj.id, "ann_type": "procurement",
                                            "round_number": 3, "project_intro": "验收用"})
    body = r.get_json() or {}
    from models.announcement import Announcement
    ann = db.session.execute(db.select(Announcement).filter_by(
        project_id=proj.id, ann_type="procurement").order_by(Announcement.id.desc())).scalars().first()
    if r.status_code in (200, 201) and ann:
        check("① 前端传第三次也被纠正成第六次", ann.round_number == 6, f"→第{ann.round_number}次")
        db.session.delete(ann); db.session.commit()
    else:
        check("① 建公告接口可用", False, f"HTTP {r.status_code} {body.get('error','')[:60]}")
    proj.round, proj.doc_confirmed, proj.officer = old_round, old_conf, old_off
    db.session.commit()

# ═══ ② 合同闸门 ═══════════════════════════════════════════════════
print("\n── ② 中标通知书前置 + 归档必填 ──")
p2 = db.session.execute(db.select(Project).where(
    Project.agency_code != "", db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
    db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
)).scalars().first()
p2.round = p2.round or 1
db.session.commit()
PKG_NO = 97           # 造一个不打架的包号
pkg = db.session.execute(db.select(Package).filter_by(project_id=p2.id, package_no=PKG_NO)).scalar_one_or_none()
if pkg is None:
    pkg = Package(project_id=p2.id, package_no=PKG_NO, name="验收包")
    db.session.add(pkg)
pkg.status, pkg.won_round = "已中标", p2.round
db.session.commit()
# 先清掉本轮中标通知书
olds = db.session.execute(db.select(ProcurementDocAttachment).filter_by(
    project_id=p2.id, kind="award_notice", round_number=p2.round)).scalars().all()
stash = [(a.original_name, a.saved_name) for a in olds]
for a in olds: db.session.delete(a)
db.session.commit()

off2 = acct("acc_off_ct", p2.officer or "验收经办人", "officer")
if not p2.officer:
    p2.officer = "验收经办人"; db.session.commit()
    off2 = acct("acc_off_ct", "验收经办人", "officer")
sc = login(off2)

r = sc.post("/api/contracts", json={"project_id": p2.id, "package_no": str(PKG_NO),
                                    "contract_name": "验收合同"})
check("② 没传中标通知书不许建合同", r.status_code == 400
      and "中标通知书" in ((r.get_json() or {}).get("error", "")),
      f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:40]}")

# 造一份中标通知书，合同应能建起来
note = ProcurementDocAttachment(project_id=p2.id, kind="award_notice", round_number=p2.round,
                                original_name="验收中标通知书.pdf", saved_name="acc_test.pdf")
db.session.add(note); db.session.commit()
r = sc.post("/api/contracts", json={"project_id": p2.id, "package_no": str(PKG_NO),
                                    "contract_name": "验收合同"})
check("② 传了中标通知书就能建合同", r.status_code == 200,
      f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:60]}")
cid = ((r.get_json() or {}).get("data") or {}).get("id")

if cid:
    c = db.session.get(Contract, cid)
    c.status = "审核完成"; c.file_saved_name = ""; c.file_name = ""
    c.sign_date = c.service_start = c.service_end = ""
    db.session.commit()
    r = sc.post(f"/api/contracts/{cid}/submit", json={})
    check("② 没传盖章合同不许归档", r.status_code == 400
          and "盖章" in ((r.get_json() or {}).get("error", "")),
          f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:40]}")

    c.file_saved_name, c.file_name = "x.pdf", "盖章合同.pdf"
    c.sign_date = "2026年8月1日"
    db.session.commit()
    r = sc.post(f"/api/contracts/{cid}/submit", json={})
    err = (r.get_json() or {}).get("error", "")
    check("② 生效时间/有效期没填不许归档", r.status_code == 400
          and "生效" in err and "有效期" in err, f"HTTP {r.status_code} {err[:60]}")

    c.service_start, c.service_end = "2026年8月10日", "2027年8月9日"
    db.session.commit()
    r = sc.post(f"/api/contracts/{cid}/submit", json={})
    check("② 盖章件+三个日期齐了才准归档", r.status_code == 200,
          f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:60]}")

    # 通知书被删掉后，连传盖章件都要拦
    db.session.delete(db.session.get(ProcurementDocAttachment, note.id)); db.session.commit()
    r = sc.post(f"/api/contracts/{cid}/upload", data={})
    check("② 没通知书连传盖章件都拦", r.status_code == 400
          and "中标通知书" in ((r.get_json() or {}).get("error", "")),
          f"HTTP {r.status_code} {(r.get_json() or {}).get('error','')[:40]}")

    r = sc.get("/api/contracts")
    row = [x for x in (r.get_json() or {}).get("data", []) if x["id"] == cid]
    check("② 列表带出 award_notice_ok=False 供前端提示",
          bool(row) and row[0].get("award_notice_ok") is False,
          f"→{row[0].get('award_notice_ok') if row else '没查到'}")
    db.session.delete(db.session.get(Contract, cid)); db.session.commit()

# 收拾现场
db.session.delete(pkg)
for on, sn in stash:
    db.session.add(ProcurementDocAttachment(project_id=p2.id, kind="award_notice",
                                            round_number=p2.round, original_name=on, saved_name=sn))
db.session.commit()

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)} 项：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
