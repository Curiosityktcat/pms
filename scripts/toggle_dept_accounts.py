#!/usr/bin/env python3
"""启用/停用全部科室门户账号。

为什么需要它：账号是在服务重启前建好的，而当时线上跑的还是旧代码——旧代码不认识
dept 这个角色，can_view_project 对陌生角色是默认放行的，科室账号那会儿登进来会看到
全部项目。所以先建后停，等新代码起来了再启用。

  python toggle_dept_accounts.py on    # 启用（服务重启、确认新代码生效后再跑）
  python toggle_dept_accounts.py off   # 停用
"""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/pms/backend"))

import app as A
from models import db
from models.user import User


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("on", "off"):
        print(__doc__)
        sys.exit(2)
    want = 1 if sys.argv[1] == "on" else 0

    a = A.create_app()
    with a.app_context():
        users = list(db.session.execute(
            db.select(User).filter_by(role="dept")).scalars())
        if not users:
            print("没有科室账号")
            return
        for u in users:
            u.active = want
        db.session.commit()
        print("%s %d 个科室账号：%s" % ("启用" if want else "停用", len(users),
                                    "、".join(u.username for u in users)))
        if want:
            print("\n请确认服务已加载新代码：科室账号登录后应只看到「我的科室项目」一个菜单。")


if __name__ == "__main__":
    main()
