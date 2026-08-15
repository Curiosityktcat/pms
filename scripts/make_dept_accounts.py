"""为每个归口科室建一个只读门户账号。

幂等：账号已存在就只补 role/dept_code，不重置密码（重置会把已经发出去的密码作废）。
密码在本机生成，只写进 600 权限的文件，不走命令行参数。
"""
import os
import secrets
import string
import sys

sys.path.insert(0, os.path.expanduser("~/pms/backend"))

import app as A
from models import db
from models.user import User
from services import dept as dept_svc
from services.auth import hash_pw

OUT = os.path.expanduser("~/pms/data/dept_accounts.txt")

# 去掉容易看错的 0/O/1/l/I，科室是手抄密码进浏览器的
ALPHABET = "".join(c for c in (string.ascii_letters + string.digits) if c not in "0O1lI")


def gen_pw(n=10):
    return "".join(secrets.choice(ALPHABET) for _ in range(n))


def main():
    a = A.create_app()
    with a.app_context():
        existing = {u.username: u for u in db.session.execute(db.select(User)).scalars()}
        made = []
        for d in dept_svc.list_depts():
            uname = d.name
            if uname in existing and existing[uname].role != "dept":
                # 已被别的角色占用（如 审计科 是个监督账号），换个不冲突的用户名
                uname = "%s-科室" % d.name
            u = existing.get(uname)
            if u and u.role == "dept":
                changed = False
                if (u.dept_code or "") != d.code:
                    u.dept_code = d.code
                    changed = True
                if changed:
                    db.session.commit()
                made.append((uname, "（已存在，密码未变）", d.code, d.name))
                continue
            pw = gen_pw()
            salt = secrets.token_hex(16)
            db.session.add(User(username=uname, salt=salt, pw_hash=hash_pw(pw, salt),
                                role="dept", display_name=d.name, active=1,
                                agency_code="", dept_code=d.code))
            db.session.commit()
            made.append((uname, pw, d.code, d.name))

        lines = ["PMS 科室门户账号（角色：归口科室，只读）",
                 "生成时间：由脚本写入，密码仅此一份，请发给对应科室后妥善保管。",
                 "登录地址：内网 http://172.1.14.12:1573  外网 https://pms.curiosityktcat.cn",
                 "",
                 "%-16s %-14s %-8s %s" % ("用户名", "密码", "科室码", "科室")]
        for uname, pw, code, name in made:
            lines.append("%-16s %-14s %-8s %s" % (uname, pw, code, name))
        text = "\n".join(lines) + "\n"

        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        fd = os.open(OUT, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        print(text)
        print("已写入 %s（权限 600）" % OUT)


if __name__ == "__main__":
    main()
