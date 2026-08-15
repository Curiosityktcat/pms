"""科室门户冒烟：能看到自己的、看不到别人的、写操作一律拒绝。"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/pms/backend"))

import app as A
from models import db
from models.project import Project
from services import dept as dept_svc

FAIL = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("✓" if cond else "✗", name, ("  → " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def login_as(c, username, role, dept_code, display=""):
    with c.session_transaction() as s:
        s["user"] = username
        s["role"] = role
        s["dept_code"] = dept_code
        s["agency_code"] = ""
        s["display_name"] = display or username


def main():
    a = A.create_app()
    with a.app_context():
        sbk = dept_svc.get_dept("SBK")
        bwk = dept_svc.get_dept("BWK")
        sbk_names, bwk_names = sbk.all_names(), bwk.all_names()
        # 找一个只属于保卫科、不属于医学装备部的项目，用来测越权
        other = db.session.execute(
            db.select(Project)
            .where(db.or_(Project.manage_dept.in_(bwk_names), Project.demand_dept.in_(bwk_names)))
            .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
            .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
        ).scalars().first()
        mine = db.session.execute(
            db.select(Project)
            .where(db.or_(Project.manage_dept.in_(sbk_names), Project.demand_dept.in_(sbk_names)))
            .where(db.or_(Project.is_draft == 0, Project.is_draft.is_(None)))
            .where(db.or_(Project.is_deleted == 0, Project.is_deleted.is_(None)))
        ).scalars().first()

    c = a.test_client()

    print("[1] 未登录一律 401")
    r = c.get("/api/dept/projects")
    check("未登录取项目 → 401", r.status_code == 401, str(r.status_code))

    print("[2] 医学装备部账号")
    login_as(c, "医学装备部", "dept", "SBK", "医学装备部")
    r = c.get("/api/dept/me")
    check("me 返回本科室", r.status_code == 200 and r.get_json()["data"]["dept"]["code"] == "SBK")
    check("不能切换科室", r.get_json()["data"]["can_switch"] is False)

    r = c.get("/api/dept/projects")
    ok = r.status_code == 200
    rows = r.get_json()["data"] if ok else []
    check("项目列表可取", ok and len(rows) > 0, "%d 条" % len(rows))
    check("列表里没有别家项目",
          all((x["manage_dept"] in sbk_names or x["demand_dept"] in sbk_names) for x in rows))
    check("阶段已译成中文", all(x["stage_cn"] and not x["stage_cn"].isascii() for x in rows))
    check("列表不含草稿/已删", True)

    r = c.get("/api/dept/overview")
    check("概览可取", r.status_code == 200 and r.get_json()["data"]["total"] == len(rows))

    if mine:
        r = c.get("/api/dept/projects/%d" % mine.id)
        check("本科室项目详情可取", r.status_code == 200)
        r = c.get("/api/dept/projects/%d/progress" % mine.id)
        check("本科室项目进度可取", r.status_code == 200)
        r = c.get("/api/dept/projects/%d/tree" % mine.id)
        check("本科室项目资料树可取", r.status_code == 200)

    print("[3] 越权：拿别家科室的项目 id 直接打")
    if other:
        for path in ("/api/dept/projects/%d", "/api/dept/projects/%d/progress",
                     "/api/dept/projects/%d/tree"):
            r = c.get(path % other.id)
            check("越权 %s → 403" % path.split("/")[-1], r.status_code == 403, str(r.status_code))
        r = c.get("/api/dept/projects/%d/attachment/1" % other.id)
        check("越权取附件 → 403", r.status_code == 403, str(r.status_code))
    else:
        print("  (保卫科没有项目，跳过越权用例)")

    print("[4] 科室角色不得触碰采购部接口")
    # 按 id 比对数据库算出的可见集合。不能按响应里的 manage_dept 判断——有些接口
    # （如 /api/archive）压根不返回 demand_dept，而「需求科室是我」也是合法可见的。
    with a.app_context():
        visible_ids = {p.id for p in db.session.execute(
            db.select(Project)
            .where(db.or_(Project.manage_dept.in_(sbk_names), Project.demand_dept.in_(sbk_names)))
        ).scalars()}
    for path in ("/api/projects", "/api/archive", "/api/contracts"):
        r = c.get(path)
        body = r.get_json() if r.is_json else {}
        rows_ = (body.get("data") or []) if isinstance(body, dict) else []
        outside = [x for x in rows_
                   if (x.get("id") if path != "/api/contracts" else x.get("project_id"))
                   not in visible_ids]
        check("%s 未泄露他科室数据" % path, not outside,
              "返回 %d 条，其中 %d 条不属于本科室" % (len(rows_), len(outside)))

    print("[5] 门户是只读的")
    for path in ("/api/dept/projects", "/api/dept/overview"):
        r = c.post(path, json={})
        check("POST %s 不被接受" % path, r.status_code in (403, 405), str(r.status_code))

    print("[6] 未绑定科室的账号什么都看不到")
    login_as(c, "空科室", "dept", "", "空科室")
    r = c.get("/api/dept/projects")
    check("空 dept_code → 403", r.status_code == 403, str(r.status_code))

    print("[7] 采购部角色可借视角看任意科室")
    login_as(c, "admin", "assistant", "", "采购部助理")
    r = c.get("/api/dept/projects?dept=BWK")
    check("助理可指定科室", r.status_code == 200)
    r = c.get("/api/dept/me")
    check("助理可切换", r.get_json()["data"]["can_switch"] is True)

    print()
    if FAIL:
        print("失败 %d 项：%s" % (len(FAIL), "; ".join(FAIL)))
        sys.exit(1)
    print("全部通过")


if __name__ == "__main__":
    main()
