# -*- coding: utf-8 -*-
"""把采购部内部角色的权限补齐到代码里的默认值。

成因：DEFAULT_ROLE_PERMS 只在 role_permissions 表为空时播种一次，后来新增的
功能键（开标看板、采购计划池、采购需求编制那五项、人员/模板维护……）永远补不进去。
admin 账号走 is_admin_user 特判，看得见全部，所以一直没人报障。

**只做加法**：officer 多出来的「11. 归档」保留不动——那看着是有意给的，
按默认值覆盖会把它删掉，可能直接影响经办人日常。
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/pms/backend"))

import app as A
from models import db
from services.permission import DEFAULT_ROLE_PERMS, get_role_perms, PERMISSION_CATALOG

ROLES = ["leader", "assistant", "officer"]


def main():
    a = A.create_app()
    with a.app_context():
        label = {}
        for g in PERMISSION_CATALOG:
            for it in g.get("items", []):
                label[it["key"]] = it.get("label", it["key"])

        from models.role_permission import RolePermission
        for role in ROLES:
            cur = set(get_role_perms(role))
            want = set(DEFAULT_ROLE_PERMS.get(role, []))
            missing = want - cur
            extra = cur - want
            if not missing:
                print("%s：已齐，不动" % role)
                continue
            for key in sorted(missing):
                db.session.add(RolePermission(role=role, perm_key=key))
            db.session.commit()
            print("%s：补了 %d 项 → %s" % (
                role, len(missing), "、".join(label.get(k, k) for k in sorted(missing))))
            if extra:
                print("   （保留未在默认值里的 %s，不删）" % "、".join(
                    label.get(k, k) for k in sorted(extra)))

        print("")
        print("== 补后 ==")
        for role in ROLES:
            print("  %-10s %d 项" % (role, len(get_role_perms(role))))


if __name__ == "__main__":
    main()
