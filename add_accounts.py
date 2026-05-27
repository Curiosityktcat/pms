#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
补充账号：4个经办人 + 7个代理机构，并给 users 表加 agency_code 字段(代理机构绑定缩写,用于权限隔离)。
重复运行安全。
"""
import os, sqlite3, hashlib, secrets
DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pms.db")

def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()

# 经办人：(账号=姓名, 密码, 显示名)
OFFICERS = [
    ("黄新博", "huangxinbo"),
    ("郑跃俊", "zhengyuejun"),
    ("谭群",   "tanqun"),
    ("杨文炽", "yangwenchi"),
]
# 代理机构：(账号=全称, 缩写, 密码)
AGENCIES = [
    ("四川知行招标代理有限公司", "ZX"),
    ("内江中洲工程项目管理有限公司", "ZZ"),
    ("四川中锦招标代理有限公司", "ZJ"),
    ("四川尚璟招标代理有限责任公司", "SJ"),
    ("四川华询工程管理有限责任公司", "HX"),
    ("四川三盈招标代理有限公司", "SY"),
    ("内江市川交公路勘察设计有限公司", "CJ"),
]

def main():
    conn = sqlite3.connect(DB); c = conn.cursor()
    # 给 users 加 agency_code 列（代理机构账号绑定缩写；其它角色为空）
    cols = [r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "agency_code" not in cols:
        c.execute("ALTER TABLE users ADD COLUMN agency_code TEXT DEFAULT ''")
        print("[*] users 表已加 agency_code 列")

    def add_user(username, pw, role, display, agency_code=""):
        exists = c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
        if exists:
            print(f"    跳过(已存在): {username}")
            return
        salt = secrets.token_hex(16)
        c.execute("""INSERT INTO users(username,salt,pw_hash,role,display_name,agency_code)
                     VALUES(?,?,?,?,?,?)""",
                  (username, salt, hash_pw(pw, salt), role, display, agency_code))
        print(f"    新增: {username} / {pw}  (role={role}{', 代理='+agency_code if agency_code else ''})")

    print("[*] 添加经办人账号：")
    for name, pw in OFFICERS:
        add_user(name, pw, "officer", name)

    print("[*] 添加代理机构账号：")
    for fullname, code in AGENCIES:
        add_user(fullname, f"{code}123", "agency", fullname, code)

    conn.commit(); conn.close()
    print("[*] 完成。代理机构初始密码 = 大写缩写+123（如 ZJ123），登录后请自行修改。")

if __name__ == "__main__":
    main()
