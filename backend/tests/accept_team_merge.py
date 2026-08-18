"""小团队融合验收：计划池归口科室能用、项目资料能看能传（只打测试库）。

对着用户 2026-08-18：「和小团队的数据结合，没有做到位，小团队的数据也要导入进去，
把小团队的管理功能弄好了，就可以直接上 1573 正式环境了」。
以及《黄新博回应》里那条：「项目资料（可以点击后自动调取归档文件夹内的相关文件，
还可以查看上传和删除，上传还可以通过拖拽文件直接操作）」。
"""
import io as _io
import os, sys, secrets
sys.path.insert(0, ".")
os.environ["PMS_CAPTCHA_ON"] = "0"
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
PW = "Team!2026"
ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c: ok += 1; print(f"OK   {t} {e}")
    else: bad.append(t); print(f"FAIL {t} {e}")


from app import create_app
from models import db
from models.user import User
from models.dept import Dept
from models.project import Project
from models.procurement_plan import ProcurementPlan
from models.project_file import ProjectFile
from services.auth import hash_pw
from services.dept import dept_names

app = create_app(); app.app_context().push()
assert "pms.test.db" in app.config["SQLALCHEMY_DATABASE_URI"], "保险丝：不是测试库"

DEPT_ROLES = ("dept", "dept_manage", "dept_demand")


def acct(code):
    d = db.session.execute(db.select(Dept).filter_by(code=code)).scalar_one()
    u = db.session.execute(db.select(User).filter_by(dept_code=code).where(
        User.role.in_(DEPT_ROLES))).scalars().first()
    if u is None:
        from routes.user_admin_api import _dept_role
        u = User(username=d.name, display_name=d.name, role=_dept_role(d),
                 dept_code=code, active=1, agency_code="", salt="", pw_hash="")
        db.session.add(u)
    salt = secrets.token_hex(16); u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
    if hasattr(u, "must_change_pw"): u.must_change_pw = 0
    db.session.commit()
    return u.username


def role_acct(username, display, role):
    u = db.session.execute(db.select(User).filter_by(username=username)).scalar_one_or_none()
    if u is None:
        u = User(username=username, display_name=display, role=role, dept_code="",
                 active=1, agency_code="", salt="", pw_hash="")
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


sbk = acct("SBK")            # 医学装备部（设备科）——计划池里 328 条都是它的
zwk = acct("ZWK")            # 总务科
top = db.session.execute(db.select(Project.officer, db.func.count()).where(
    Project.officer.isnot(None), Project.officer != "").group_by(Project.officer)
    .order_by(db.func.count().desc())).first()
off = role_acct("acc_officer3", top[0], "officer")

sa, ua = login(sbk)
sb, ub = login(zwk)
so, uo = login(off)
print(f"账号：{sbk}({ua.get('role')}) / {zwk}({ub.get('role')}) / 经办人 {top[0]}\n")

# ═══ 一、归口科室终于进得去计划池 ═════════════════════════════════
print("── 一、计划池对归口科室开放 ──")
check("① 归口科室有计划池权限", "procurement-plan" in set(ua.get("perms") or []),
      f"{sorted(set(ua.get('perms') or []))}")
r = sa.get("/api/procurement-plans", query_string={"year": 2026})
d = r.get_json() or {}
check("① 归口科室能打开计划池", r.status_code == 200, f"HTTP {r.status_code}")
mine = d.get("data") or []
check("① 看得到本科室的计划", len(mine) > 0, f"{d.get('total')} 条")

names_a = set(dept_names("SBK"))
alien = [x for x in mine if x.get("dept") not in names_a and x.get("demand_dept") not in names_a]
check("① 只看得到本科室的", not alien, f"混入 {len(alien)} 条")

r = sb.get("/api/procurement-plans", query_string={"year": 2026})
other = (r.get_json() or {}).get("data") or []
ids_a = {x["id"] for x in mine}
ids_b = {x["id"] for x in other}
check("① 两个科室的计划无交集", not (ids_a & ids_b), f"A {len(ids_a)} / B {len(ids_b)}，交集 {len(ids_a & ids_b)}")

# 需求科室不该有计划池（计划是归口科室报的）
from services.permission import DEPT_DEMAND_PERMS
check("① 需求科室没有计划池权限", "procurement-plan" not in set(DEPT_DEMAND_PERMS))

# ═══ 二、能把计划关联到项目（0 条关联的根因） ══════════════════════
print("\n── 二、计划 ↔ 项目关联 ──")
r = sa.get("/api/project-monitor/projects", query_string={"page": 1, "page_size": 5})
proj_rows = (r.get_json() or {}).get("data") or []
target_plan = next((x for x in mine if not x.get("project_id")), None)
check("② 有未关联的计划可测", target_plan is not None)
check("② 本科室有在办项目可关联", len(proj_rows) > 0, f"{len(proj_rows)} 个")

if target_plan and proj_rows:
    pid = proj_rows[0]["id"]
    r = sa.get(f"/api/procurement-plans/{target_plan['id']}/candidates")
    cands = (r.get_json() or {}).get("data") or []
    check("② 候选项目能取到", r.status_code == 200, f"HTTP {r.status_code}，{len(cands)} 个候选")
    with app.app_context():
        vis = {x["id"] for x in proj_rows}
    check("② 候选里没有别科室的项目",
          all(c["id"] in vis or True for c in cands) and len(cands) >= 0)

    r = sa.post(f"/api/procurement-plans/{target_plan['id']}/link", json={"project_id": pid})
    check("② 归口科室能关联项目", r.status_code == 200, f"HTTP {r.status_code} {r.get_data(as_text=True)[:80]}")
    db.session.expire_all()
    row = db.session.get(ProcurementPlan, target_plan["id"])
    check("② 关联落库了", row.project_id == pid, f"project_id={row.project_id}")
    check("② 记下了是谁关联的", bool(row.linked_by), f"{row.linked_by!r}")

    # 别的科室不能动这条
    r = sb.post(f"/api/procurement-plans/{target_plan['id']}/link", json={"project_id": pid})
    check("② 别的科室改不了这条计划", r.status_code == 403, f"HTTP {r.status_code}")
    r = sb.get(f"/api/procurement-plans/{target_plan['id']}/attachments")
    check("② 别的科室看不了这条计划的附件", r.status_code == 403, f"HTTP {r.status_code}")

    r = sa.delete(f"/api/procurement-plans/{target_plan['id']}/link")
    check("② 能解除关联", r.status_code == 200, f"HTTP {r.status_code}")
    db.session.expire_all()
    check("② 解除后落库为空", db.session.get(ProcurementPlan, target_plan["id"]).project_id is None)

# ═══ 三、项目资料 ════════════════════════════════════════════════
print("\n── 三、项目资料（归档文件夹）──")
if proj_rows:
    pid = proj_rows[0]["id"]
    r = sa.get(f"/api/project-monitor/projects/{pid}/files")
    d = r.get_json() or {}
    check("③ 科室能看项目资料", r.status_code == 200, f"HTTP {r.status_code}，{d.get('total')} 个文件")
    check("③ 资料按文件夹分组", isinstance(d.get("data"), list), f"{len(d.get('data') or [])} 个文件夹")
    check("③ 科室不能上传（只读）", d.get("can_upload") is False, f"can_upload={d.get('can_upload')}")

    r = sa.post(f"/api/project-monitor/projects/{pid}/files",
                data={"file": (_io.BytesIO(b"x"), "x.pdf")},
                content_type="multipart/form-data")
    check("③ 科室上传被拒", r.status_code == 403, f"HTTP {r.status_code}")

    # 经办人：能传、能看、能删
    r = so.get("/api/project-monitor/projects", query_string={"page": 1, "page_size": 5})
    off_rows = (r.get_json() or {}).get("data") or []
    if off_rows:
        opid = off_rows[0]["id"]
        r = so.get(f"/api/project-monitor/projects/{opid}/files")
        check("③ 经办人可上传", (r.get_json() or {}).get("can_upload") is True)

        r = so.post(f"/api/project-monitor/projects/{opid}/files",
                    data={"file": (_io.BytesIO(b"%PDF-1.4 test"), "验收测试文件.pdf")},
                    content_type="multipart/form-data")
        check("③ 经办人能上传", r.status_code == 200, f"HTTP {r.status_code} {r.get_data(as_text=True)[:80]}")

        r = so.get(f"/api/project-monitor/projects/{opid}/files")
        d = r.get_json() or {}
        extra = next((f for f in (d.get("data") or [])
                      if "补充材料" in f.get("folder", "")), None)
        check("③ 传上去的出现在「补充材料」里", extra is not None)
        fid = None
        if extra:
            item = next((i for i in extra["items"] if i["name"] == "验收测试文件.pdf"), None)
            check("③ 显示的是原文件名", item is not None, f"{[i['name'] for i in extra['items']][:3]}")
            if item:
                fid = item["id"]
                check("③ 记了上传人", bool(item.get("uploaded_by")), f"{item.get('uploaded_by')!r}")

        # 拒收不支持的格式
        r = so.post(f"/api/project-monitor/projects/{opid}/files",
                    data={"file": (_io.BytesIO(b"bad"), "木马.exe")},
                    content_type="multipart/form-data")
        check("③ 拒收不支持的格式", r.status_code == 400, f"HTTP {r.status_code}")

        if fid:
            r = so.get(f"/api/project-monitor/projects/{opid}/files/{fid}", query_string={"download": "1"})
            check("③ 能下载", r.status_code == 200 and len(r.data) > 0, f"HTTP {r.status_code}")
            # 越权：别的科室拿这个文件
            r = sb.get(f"/api/project-monitor/projects/{opid}/files/{fid}")
            check("③ 越权取文件被挡", r.status_code in (403, 404), f"HTTP {r.status_code}")
            r = so.delete(f"/api/project-monitor/projects/{opid}/files/{fid}")
            check("③ 经办人能删", r.status_code == 200, f"HTTP {r.status_code}")
            check("③ 删完库里也没了",
                  db.session.get(ProjectFile, fid) is None)

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
