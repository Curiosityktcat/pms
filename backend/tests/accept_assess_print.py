"""代理机构考核三项改动的验收（只打测试库）。

黄新博 2026-09-03 提的三条：
  1. 要能打印、导成 Excel，打印最多 2 页 A4（好双面印）
  2. 「主动脉内球囊反搏」那个项目公告驳回次数不对（页面上扣了 27 分）
  3. 归档时效「缺少时间数据」，要能用日历手填资料交接与备案送达时间再算分

第 2 条的真因：测试脚本写死过 project_id，留下一批 target_id 指向别家项目
公告的假驳回。所以这里不只验分数，还专门造一条「跨项目的驳回」，
确认它不被计入——这类脏数据以后还会有，判据必须挡得住。
"""
import os
import re
import secrets
import sys

sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Agc!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c:
        ok += 1
        print(f"OK   {t} {e}")
    else:
        bad.append(t)
        print(f"FAIL {t} {e}")


from app import create_app                      # noqa: E402
from models import db                           # noqa: E402
from models.user import User                    # noqa: E402
from models.project import Project              # noqa: E402
from models.announcement import Announcement    # noqa: E402
from models.approval_log import ApprovalLog     # noqa: E402
from services.auth import hash_pw               # noqa: E402
from services import agency_assessment as svc   # noqa: E402
from services import agency_assessment_sheet as sheet  # noqa: E402

app = create_app()
app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"


def login_admin():
    u = db.session.execute(
        db.select(User).filter_by(username="admin")).scalars().first()
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
    if hasattr(u, "must_change_pw"):
        u.must_change_pw = 0
    db.session.commit()
    c = app.test_client()
    c.post("/api/auth/login", json={"username": u.username, "password": PW})
    return c


c = login_admin()

proj = db.session.execute(db.select(Project).where(
    Project.agency_code != "", Project.name.like("%主动脉内球囊%"))).scalars().first()
if proj is None:
    proj = db.session.execute(db.select(Project).where(
        Project.agency_code != "")).scalars().first()
print(f"用例项目：{proj.id} {proj.name}")

# ── 1. 驳回只认本项目自己的公告 ───────────────────────────────────
own = db.session.execute(db.select(Announcement.id)
                         .filter_by(project_id=proj.id)).scalars().all()
alien = db.session.execute(db.select(Announcement.id)
                           .where(Announcement.project_id != proj.id)).scalars().first()
base = svc.auto_scores(proj)
base.pop("LADDER_DATES")
m = re.search(r"公告被驳回 (\d+) 次", base["ann_irregular"][1])
n_before = int(m.group(1)) if m else -1
check("公告驳回次数已排除跨项目脏数据", 0 <= n_before < 5,
      f"当前算出 {n_before} 次：{base['ann_irregular'][1]}")

fake = ApprovalLog(project_id=proj.id, node="announcement", target_id=alien,
                   action="reject", reason="验收造的跨项目假驳回",
                   operator="accept_test", created_at="2026-09-03T00:00:00")
db.session.add(fake)
db.session.commit()
after = svc.auto_scores(proj)
after.pop("LADDER_DATES")
m2 = re.search(r"公告被驳回 (\d+) 次", after["ann_irregular"][1])
check("跨项目的驳回不计入本项目", int(m2.group(1)) == n_before,
      f"造假后仍是 {m2.group(1)} 次")

if own:
    fake.target_id = own[0]
    db.session.commit()
    real = svc.auto_scores(proj)
    real.pop("LADDER_DATES")
    m3 = re.search(r"公告被驳回 (\d+) 次", real["ann_irregular"][1])
    check("本项目自己公告的驳回照常计入", int(m3.group(1)) == n_before + 1,
          f"改成本项目公告后 {m3.group(1)} 次")
db.session.delete(fake)
db.session.commit()

# ── 2. 三项时效可手填日期 ─────────────────────────────────────────
d = svc.norm_dates({"archive_speed": {"start": "2026-06-20", "end": "2026-06-23"},
                    "bogus_key": {"start": "x"}})
check("手填日期解析正常、脏 key 被丢掉",
      d == {"archive_speed": {"start": "2026-06-20", "end": "2026-06-23"}}, str(d))

a = svc.auto_scores(proj, d)
a.pop("LADDER_DATES")
check("归档按手填日期算分（3 日内 +0.5）",
      a["archive_speed"][0] == 0.5, a["archive_speed"][1])

a2 = svc.auto_scores(proj, {"archive_speed": {"start": "2026-06-20", "end": "2026-06-21"}})
a2.pop("LADDER_DATES")
check("归档 1 日内 +1.5", a2["archive_speed"][0] == 1.5, a2["archive_speed"][1])

a3 = svc.auto_scores(proj, {"archive_speed": {"start": "2026-06-20", "end": "2026-07-20"}})
a3.pop("LADDER_DATES")
check("归档超期按每日 0.3 扣", a3["archive_speed"][0] == round(-0.3 * 27, 2),
      a3["archive_speed"][1])

a4 = svc.auto_scores(proj, {"archive_speed": {"start": "2026-06-23", "end": "2026-06-20"}})
a4.pop("LADDER_DATES")
check("日期填反了不给分、给提示", a4["archive_speed"][0] is None, a4["archive_speed"][1])

items = svc.build_items(proj, None, d)
row = next(i for i in items if i["key"] == "archive_speed")
check("评分行带上日历要用的标签与日期",
      row["start_label"] == "资料交接时间" and row["end_label"] == "备案资料送达时间"
      and row["date_source"] == "manual",
      f"{row['start_label']}/{row['end_label']}/{row['date_source']}")

# ── 3. 导出 Excel 与打印页 ────────────────────────────────────────
r = c.get(f"/api/agency-assessments/project/{proj.id}/export.xlsx")
check("导出 Excel 200", r.status_code == 200, str(r.status_code))
check("是 xlsx 且非空", r.data[:2] == b"PK" and len(r.data) > 4000, f"{len(r.data)} bytes")

r2 = c.get(f"/api/agency-assessments/project/{proj.id}/print")
html = r2.get_data(as_text=True)
check("打印页 200", r2.status_code == 200, str(r2.status_code))
for seg in ("一、基本信息", "二、考核内容及评分标准", "三、一票否决项目", "四、综合评价"):
    check(f"打印页含「{seg}」", seg in html)
check("打印页锁 A4 且自动收进两页",
      "size: A4 portrait" in html and "297 - 20) * 2" in html)
check("打印页 15 个评分项一个不少",
      all(it["name"][:12] in html for it in svc.ITEMS))

long_note = "代理机构在本环节存在明显拖延，经采购部两次书面催办后仍未按期提交。" * 3
items_long = svc.build_items(proj, None, d)
for i in items_long:
    i["note"] = long_note
data = sheet.build_rows({"project_name": proj.name, "project_number": proj.number,
                         "agency_name": "验收用", "veto": ["v1"], "veto_note": long_note,
                         "subj_timeliness": "满意", "subj_ability": "一般",
                         "subj_attitude": "满意", "comment": long_note,
                         "status": "已提交", "assessor": "验收",
                         "assessed_at": "2026-09-03T10:00:00"},
                        items_long)
xb = sheet.to_xlsx(data)
check("备注写满也能出 Excel", xb[:2] == b"PK" and len(xb) > 4000, f"{len(xb)} bytes")
check("一票否决勾了就带事实依据", "一票否决事实依据" in sheet.to_print_html(data))
check("勾选项打成 ☑/□",
      "☑" in sheet.to_print_html(data) and "□" in sheet.to_print_html(data))

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)} 项：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
