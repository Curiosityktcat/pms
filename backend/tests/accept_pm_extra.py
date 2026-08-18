"""项目管理器补充验收：主脚本里因数据不足被跳过的两条。

① 科室改 URL 取「他科室的在办项目」时间线 → 必须 403（主脚本里 ZWK 在办数为 0 被跳过）
② 计划池条目关联到项目后，页签要显示该项目的当前进度（库里本来一条关联都没有）
临时造数，跑完回滚。
"""
import os
import sys
import secrets

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
os.environ["PMS_CAPTCHA_ON"] = "0"

PW = "Monitor!2026"
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
from models.project import Project
from models.procurement_plan import ProcurementPlan
from services.auth import hash_pw

app = create_app()
ctx = app.app_context()
ctx.push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

DEPT_ROLES = ("dept", "dept_manage", "dept_demand")
A_CODE = "SBK"      # 医学装备部


def acct(code):
    u = db.session.execute(db.select(User).filter_by(dept_code=code).where(
        User.role.in_(DEPT_ROLES))).scalars().first()
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
    db.session.commit()
    return u.username


def login(username):
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": username, "password": PW})
    return c, ((r.get_json() or {}).get("user") or {})


def all_plans():
    out, page = [], 1
    while True:
        r = sa.get("/api/project-monitor/plans", query_string={"page": page, "page_size": 100})
        body = r.get_json() or {}
        rows = body.get("data") or []
        out += rows
        if not rows or len(out) >= (body.get("total") or 0):
            return out
        page += 1


a_user = acct(A_CODE)
sa, ua = login(a_user)
from services.dept import dept_names as _dn
a_names = set(_dn(A_CODE))      # 含曾用名，必须和接口用同一套名字，否则误判「混入」
print(f"科室A = {a_user}（{'/'.join(a_names)}，角色 {ua.get('role')}）\n")

# 当前可见集合
r = sa.get("/api/project-monitor/projects", query_string={"page": 1, "page_size": 200})
mine = {x["id"] for x in (r.get_json() or {}).get("data") or []}
print(f"科室A 可见在办 {len(mine)} 个")

# ── ⑥ 找一个「在办、且不属于科室A」的项目做越权 ─────────────────
outsider = db.session.execute(
    db.select(Project.id, Project.name, Project.manage_dept, Project.demand_dept).where(
        Project.id.notin_(mine) if mine else db.true(),
        db.or_(Project.is_draft == 0, Project.is_draft.is_(None)),
        db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)),
        db.or_(Project.status != "已归档", Project.status.is_(None)),
    )).first()
if outsider:
    pid, pname, md, dd = outsider
    r = sa.get(f"/api/project-monitor/projects/{pid}/timeline")
    check("⑥ 科室改URL取他科室在办项目的时间线被挡", r.status_code == 403,
          f"HTTP {r.status_code}（项目 {pid} 归口={md} 需求={dd}）")
    body = r.get_json() or {}
    check("⑥ 被挡时不泄露项目信息", pname not in str(body), f"{str(body)[:60]}")
else:
    check("⑥ 找得到他科室的在办项目", False, "库里没有可用于越权测试的项目")

# ── ⑤ 造一条「计划已关联项目」的数据 ────────────────────────────
target_plan = db.session.execute(
    db.select(ProcurementPlan).where(
        db.or_(ProcurementPlan.dept.in_(a_names), ProcurementPlan.demand_dept.in_(a_names)),
        ProcurementPlan.project_id.is_(None))).scalars().first()
link_pid = sorted(mine)[0] if mine else None
rollback = None
if target_plan is not None and link_pid:
    rollback = (target_plan.id, target_plan.project_id)
    target_plan.project_id = link_pid
    db.session.commit()
    proj = db.session.get(Project, link_pid)
    print(f"临时关联：计划 #{target_plan.id}「{target_plan.name}」→ 项目 {link_pid}「{proj.name}」")

    rows = all_plans()      # page_size 上限 100，必须翻页
    row = next((x for x in rows if x["id"] == target_plan.id), None)
    check("⑤ 关联后计划条目出现在页签里", row is not None)
    if row:
        check("⑤ 状态变成「已立项」", row.get("plan_status") == "已立项", f"{row.get('plan_status')}")
        pr = row.get("project") or {}
        check("⑤ 带出项目编号与名称", bool(pr.get("name")), f"{pr.get('number')} {pr.get('name')}")
        check("⑤ 带出当前阶段", bool(pr.get("stage_label")), f"阶段={pr.get('stage_label')}")
        check("⑤ 带出当前处理人", "pending" in pr,
              f"处理人={(pr.get('pending') or {}).get('owner_name')} "
              f"卡{(pr.get('pending') or {}).get('waiting_days')}天")
        check("⑤ 已立项的不再标超期红", not row.get("overdue"))
else:
    check("⑤ 找得到可关联的计划条目", False, "本科室没有未关联的计划，或没有可见项目")

# ── 顺带：科室拿别人的计划？plans 只按会话科室码取，验一下别科室计划不在里面 ──
rows = all_plans()
alien = [x for x in rows if x.get("dept") and x["dept"] not in a_names
         and x.get("demand_dept") not in a_names]
check("⑤ 计划页签只出本科室的", not alien, f"混入 {len(alien)} 条")

# 回滚
if rollback:
    pid_, old = rollback
    db.session.get(ProcurementPlan, pid_).project_id = old
    db.session.commit()
    print(f"已回滚计划 #{pid_} 的关联")

print(f"\n通过 {ok_count} 项" + (f"，失败 {len(bad)} 项：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
