"""把测试库的 admin 口令恢复成《PMS测试环境访问方式》里写的那个。

--reset 会把测试库整个换成正式库的副本，admin 口令随之变回正式库的。
但文档已经发给用户了，口令必须跟文档一致，否则他登不进去（2026-08-15 就因为
验收脚本改掉口令让他吃过一次闭门羹）。
"""
import os
import re
import secrets
import sys

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"

DOC = "/home/huangxb/files/PMS测试环境访问方式_2026-08-15.md"
m = re.search(r"密码：`([^`]+)`", open(DOC, encoding="utf-8").read())
assert m, "文档里没找到密码"
PW = m.group(1)

from app import create_app
from models import db
from models.user import User
from services.auth import hash_pw

app = create_app()
with app.app_context():
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert "pms.test.db" in uri, f"保险丝：不是测试库 {uri}"
    u = db.session.execute(db.select(User).filter_by(username="admin")).scalar_one()
    salt = secrets.token_hex(16)
    u.salt, u.pw_hash, u.active = salt, hash_pw(PW, salt), 1
    if hasattr(u, "must_change_pw"):
        u.must_change_pw = 0
    db.session.commit()
    print(f"admin 口令已恢复成文档里那个（{PW[:2]}…{PW[-2:]}，共 {len(PW)} 位）")
