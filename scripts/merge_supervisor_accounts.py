# -*- coding: utf-8 -*-
"""审计科两个账号合并；纪委办公室补上监督角色。

黄新博 2026-08-20：
  「审计科的项目会由纪委来监督，纪委也是监督，但是监督的活 90% 都是审计科干，
    纪委监督的时候少。」

所以：
  · 审计科的监督账号绑上 SJK，一个账号同时是监督和本科室归口，
    停用多出来的「审计科-科室」。
  · 纪委办公室原来只是归口科室角色，权限里没有监督——它监督不了审计科的项目，
    上面那句制衡在系统里其实不存在。补成监督角色（监督权限是归口的超集，
    只增不减），科室绑定 JWB 保留。

密码不动：纪委那个账号的一次性密码仍然是 8-19 表里的那个。
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/pms/backend"))

import app as A
from models import db
from models.user import User
from models.user_audit_log import UserAuditLog


def main():
    apply = "--apply" in sys.argv
    a = A.create_app()
    with a.app_context():
        def get(name):
            return db.session.execute(db.select(User).filter_by(username=name)).scalar_one_or_none()

        sup = get("审计科")           # 监督岗，原来没绑科室
        dept = get("审计科-科室")      # 8-14 建的科室账号
        jw = get("纪委办公室")

        plan = []
        if sup and not sup.dept_code:
            plan.append(("审计科", "绑定科室 SJK（原来为空）"))
        if dept and dept.active:
            plan.append(("审计科-科室", "停用（身份已并入「审计科」）"))
        if jw and jw.role != "supervisor":
            plan.append(("纪委办公室", "角色 %s → supervisor（监督权限是归口的超集）" % jw.role))

        if not plan:
            print("没有要改的")
            return
        for u, what in plan:
            print("  %-14s %s" % (u, what))
        if not apply:
            print("\n这是预演。加 --apply 才真写。")
            return

        if sup and not sup.dept_code:
            sup.dept_code = "SJK"
            if not (sup.display_name or "").strip().startswith("审计科-"):
                sup.display_name = "审计科-刘堇羽"
            db.session.add(UserAuditLog(
                actor="admin", actor_name="系统维护", action="update",
                target_id=sup.id, target_username=sup.username,
                detail='{"source":"merge_supervisor_accounts","dept_code":"SJK",'
                       '"why":"监督岗同时是本科室归口"}'))
        if dept and dept.active:
            dept.active = 0
            db.session.add(UserAuditLog(
                actor="admin", actor_name="系统维护", action="toggle-active",
                target_id=dept.id, target_username=dept.username,
                detail='{"source":"merge_supervisor_accounts","active":0,'
                       '"why":"已并入监督账号「审计科」"}'))
        if jw and jw.role != "supervisor":
            before = jw.role
            jw.role = "supervisor"
            db.session.add(UserAuditLog(
                actor="admin", actor_name="系统维护", action="update",
                target_id=jw.id, target_username=jw.username,
                detail='{"source":"merge_supervisor_accounts","role":{"before":"%s",'
                       '"after":"supervisor"},"why":"纪委也是监督，需能监督审计科的项目"}'
                       % before))
        db.session.commit()
        print("\n已提交")


if __name__ == "__main__":
    main()
