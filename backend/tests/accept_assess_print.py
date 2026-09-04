"""代理机构考核三项改动的验收（只打测试库）。

黄新博 2026-09-03 提的三条：
  1. 要能打印、导成 Excel，打印最多 2 页 A4（好双面印）
  2. 「主动脉内球囊反搏」那个项目公告驳回次数不对（页面上扣了 27 分）
  3. 归档时效「缺少时间数据」，要能用日历手填资料交接与备案送达时间再算分

第 2 条的真因：测试脚本写死过 project_id，留下一批 target_id 指向别家项目
公告的假驳回。所以这里不只验分数，还专门造一条「跨项目的驳回」，
确认它不被计入——这类脏数据以后还会有，判据必须挡得住。
"""
import json
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

# ── 2b. 编制时效两头都取第一轮 ───────────────────────────────────
# 12 号项目走了两轮：一轮 6-02 发需求、6-02 出文件；二轮 6-15 又走一遍。
# projects.demand_confirmed_at 每轮被覆盖成 6-15，配上第一份采购文件 6-02
# 就成了「起点比终点晚 13 天」。起点必须回到第一轮。
from models.procurement_round import ProcurementRound  # noqa: E402

r1 = db.session.execute(db.select(ProcurementRound)
                        .filter_by(project_id=proj.id, round_number=1)).scalars().first()
rounds = db.session.execute(db.select(ProcurementRound)
                            .filter_by(project_id=proj.id)).scalars().all()
if r1 and len(rounds) > 1:
    a5 = svc.auto_scores(proj)
    ld5 = a5.pop("LADDER_DATES")
    d5 = ld5["doc_speed"]
    check("编制时效起点取第一轮、不取被覆盖的项目级字段",
          d5["start"][:10] == (r1.demand_confirmed_at or "")[:10],
          f"起点 {d5['start']}，第一轮需求确认 {(r1.demand_confirmed_at or '')[:10]}，"
          f"项目级字段 {(proj.demand_confirmed_at or '')[:10]}")
    check("多轮项目不再判成时间倒挂",
          not d5["start"] or not d5["end"] or d5["end"] >= d5["start"],
          f"{d5['start']} -> {d5['end']} ({d5['source']})")

# ── 2c. 后续轮次只扣超期、不重复加分 ─────────────────────────────
# 口径（黄新博 2026-09-03）：主要考核第一次的时间；后面每一轮只要超过 3 日
# 就把超期那部分扣掉，3 日内完成的不再加分。分数 = 第一轮打分 − 各轮超期扣分之和。
check("后续轮次 3 日内不扣也不加", svc._overrun_only(2) == (0.0, "用时 2 日，3 日内完成，不扣"),
      str(svc._overrun_only(2)))
check("后续轮次超 3 日按超期每日 0.3 扣",
      svc._overrun_only(10)[0] == round(-0.3 * 7, 2), str(svc._overrun_only(10)))
check("后续轮次超 30 日扣 30", svc._overrun_only(31)[0] == -30.0, str(svc._overrun_only(31)))
check("该轮没时间数据就不算、不瞎扣", svc._overrun_only(None) == (0.0, None),
      str(svc._overrun_only(None)))

# 找一个真走了多轮、且后面有轮次超期的项目，验总分是「第一轮分 + 各轮扣分」
multi = None
for pj in db.session.execute(db.select(Project).where(
        Project.agency_code != "")).scalars().all():
    ns = svc._round_numbers(pj.id)
    if len(ns) < 2:
        continue
    over = []
    for n in ns[1:]:
        st, en = svc._round_span(pj.id, n)
        dd = svc._days_between(st, en)
        if dd is not None and dd > 3:
            over.append((n, dd))
    if over:
        multi = (pj, ns, over)
        break
if multi:
    pj, ns, over = multi
    s1, e1 = svc._round_span(pj.id, 1)
    base_score, _ = svc._ladder(svc._days_between(s1, e1))
    want = round(base_score + sum(svc._overrun_only(d)[0] for _, d in over), 2)
    got = svc._doc_speed(pj.id, {})[0]
    check("多轮总分 = 第一轮打分 − 后续各轮超期扣分之和", got == want,
          f"[{pj.id}] {len(ns)} 轮，第一轮 {base_score:+g}，"
          f"超期轮 {over}，应得 {want}，实得 {got}")
else:
    # 库里现成没有超期轮次就自己造一轮：加一个第 N+1 轮，需求 6-01 发出、
    # 文件 6-11 才交（超期 7 日），验完删掉，不留痕。
    from models.procurement_round import ProcurementRound as PR
    from models.procurement_doc_attachment import ProcurementDocAttachment as PDA
    ns = svc._round_numbers(proj.id)
    nn = max(ns) + 1
    tmp_r = PR(project_id=proj.id, round_number=nn,
               demand_confirmed_at="2026-06-01T09:00:00", status="已结束",
               created_at="2026-06-01T09:00:00")
    tmp_a = PDA(project_id=proj.id, kind="doc", round_number=nn,
                original_name="验收造的采购文件.docx", saved_name="accept_tmp.docx",
                uploaded_by="accept_test", uploaded_at="2026-06-11T09:00:00")
    db.session.add_all([tmp_r, tmp_a])
    db.session.commit()
    try:
        s1, e1 = svc._round_span(proj.id, 1)
        base_score, _ = svc._ladder(svc._days_between(s1, e1))
        got, basis = svc._doc_speed(proj.id, {})[:2]
        want = round(base_score - 0.3 * 7, 2)
        check("多轮总分 = 第一轮打分 − 后续各轮超期扣分之和", got == want,
              f"造了第 {nn} 轮超期 7 日：第一轮 {base_score:+g}，应得 {want}，实得 {got}")
        check("超期的那一轮在依据里写明", f"第 {nn} 轮" in basis and "超期 7 日" in basis,
              basis[:110])
    finally:
        db.session.delete(tmp_r)
        db.session.delete(tmp_a)
        db.session.commit()

# 全库不该再有倒挂
rev = 0
for pj in db.session.execute(db.select(Project).where(
        Project.agency_code != "")).scalars().all():
    aa = svc.auto_scores(pj)
    for k, v in aa.pop("LADDER_DATES").items():
        if v.get("start") and v.get("end") and v["end"] < v["start"]:
            rev += 1
check("全库没有「完成早于起始」的时效项", rev == 0, f"倒挂 {rev} 项")

# ── 2d. 驳回问题清单：分类决定扣不扣分 ───────────────────────────
from services import approval_log as alog                      # noqa: E402
from models.approval_log import ApprovalLog as AL              # noqa: E402
from models.procurement_doc_attachment import ProcurementDocAttachment as PDA2  # noqa: E402

got = alog.norm_issues([
    {"category": "agency_doc", "text": "评分标准前后不一致"},
    {"category": "demand_change", "text": "科室改了配置要求"},
    {"category": "乱填的", "text": "应当被丢掉"},
    {"category": "agency_doc", "text": "   "},
])
check("问题清单只留合法分类、丢掉空描述", len(got) == 2, str(got))
check("只有代理机构文件问题算扣分项",
      sum(1 for i in got if i["category"] in alog.DEDUCT_KEYS) == 1, str(alog.DEDUCT_KEYS))

base_msg = svc.auto_scores(proj)["doc_messy"][0]
rj = AL(project_id=proj.id, round_number=1, node="doc", action="reject", seq=99,
        reason="验收造的驳回", created_at="2026-09-04T09:00:00",
        issues_json=json.dumps([
            {"category": "agency_doc", "text": "评分标准前后不一致"},
            {"category": "agency_doc", "text": "技术参数指向唯一品牌"},
            {"category": "demand_change", "text": "科室临时改了配置"},
        ], ensure_ascii=False))
db.session.add(rj)
db.session.commit()
try:
    a6 = svc.auto_scores(proj)
    check("2 条代理机构文件问题按每条 1.5 扣、需求调整那条不扣",
          round(a6["doc_messy"][0] - base_msg, 2) == -3.0, a6["doc_messy"][1][:100])

    # 驳回后代理再交一版：这一段作业时间要计入用时
    up = PDA2(project_id=proj.id, kind="doc", round_number=1,
              original_name="验收造的修订版.docx", saved_name="accept_fix.docx",
              uploaded_by="accept_test", uploaded_at="2026-09-06T09:00:00")
    db.session.add(up)
    db.session.commit()
    try:
        segs = svc._round_segments(proj.id, 1)
        check("驳回→调整版这一段被算进作业时长",
              any("驳回" in x[0] and x[3] == 2 for x in segs),
              str([(x[0], x[3]) for x in segs]))
        d1, detail = svc._round_days(proj.id, 1)
        check("总用时 = 各段之和", d1 == sum(x[3] for x in segs), f"{d1} / {detail[:90]}")
    finally:
        db.session.delete(up)
        db.session.commit()
finally:
    db.session.delete(rj)
    db.session.commit()

# ── 2e. 撤回后必须回到「待考核」，不能两个页签都找不到 ─────────────
# 现场原型：「2026年心脏脉冲电场消融导管配送服务采购项目」考核完撤回后，
# 待考核找不到（有考核记录就被排除），已考核也找不到（草稿没有考核时间，
# 被区间筛掉），项目凭空消失。
from models.agency_assessment import AgencyAssessment as AA    # noqa: E402
from services.assess_ready import ready_project_ids            # noqa: E402

all_proj = db.session.execute(db.select(Project).where(
    Project.agency_code != "")).scalars().all()
ready = ready_project_ids([x.id for x in all_proj])
subs = {a.project_id: a for a in db.session.execute(
    db.select(AA).filter_by(status="已提交")).scalars().all()}
cand = next((pid for pid in ready if pid in subs), None)

if cand is None:
    print("SKIP 测试库里没有「可考核且已提交」的项目，跳过撤回可见性验证")
else:
    row = subs[cand]
    keep = (row.status, row.assessed_at)
    r = c.get("/api/agency-assessments/pending-projects")
    before = {x["id"] for x in (r.get_json() or {}).get("data", [])}
    check("已提交的项目不该出现在待考核", cand not in before, f"项目 {cand}")

    row.status, row.assessed_at = "草稿", ""       # 模拟「撤回」
    db.session.commit()
    try:
        r = c.get("/api/agency-assessments/pending-projects")
        after = {x["id"] for x in (r.get_json() or {}).get("data", [])}
        check("撤回成草稿后回到「待考核」", cand in after,
              f"项目 {cand}，待考核 {len(after)} 个")
        r = c.get("/api/agency-assessments?start=2026-01&end=2026-12")
        pids = {x["project_id"] for x in (r.get_json() or {}).get("data", [])}
        check("草稿在「已考核」列表里也还看得到（按创建时间归期）", cand in pids,
              f"列表 {len(pids)} 条")
    finally:
        row.status, row.assessed_at = keep
        db.session.commit()

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
