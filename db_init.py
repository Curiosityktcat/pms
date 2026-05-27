#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目管理系统 - 数据库初始化（SQLite）
建表：agencies(代理机构) / people(人员) / users(用户) / projects(项目)
并预置：7家代理机构、5位监督人员、几个角色测试账号。
重复运行安全（IF NOT EXISTS / INSERT OR IGNORE）。
"""
import os, sqlite3, hashlib, secrets

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "pms.db")

AGENCIES = [
    ("ZX", "四川知行招标代理有限公司"),
    ("ZZ", "内江中洲工程项目管理有限公司"),
    ("ZJ", "四川中锦招标代理有限公司"),
    ("SJ", "四川尚璟招标代理有限责任公司"),
    ("HX", "四川华询工程管理有限责任公司"),
    ("SY", "四川三盈招标代理有限公司"),
    ("CJ", "内江市川交公路勘察设计有限公司"),
]
SUPERVISORS = ["刘堇羽", "王勇", "余兰", "黄河", "钟佩廷"]

# 角色测试账号：(用户名, 明文初始密码, 角色, 姓名)
# 角色：assistant采购部助理 / officer经办人 / leader负责人 / agency代理机构 / supervisor监督
USERS = [
    ("admin",    "admin123",   "assistant", "采购部助理"),
    ("officer",  "officer123", "officer",   "项目经办人"),
    ("leader",   "leader123",  "leader",    "采购部负责人"),
]

def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()

def init():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS agencies(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        active INTEGER DEFAULT 1)""")

    c.execute("""CREATE TABLE IF NOT EXISTS people(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        id_card TEXT DEFAULT '',
        photo TEXT DEFAULT '',
        role_type TEXT DEFAULT 'supervisor',   -- supervisor监督 / representative采购人代表 / both
        active INTEGER DEFAULT 1)""")

    c.execute("""CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        salt TEXT NOT NULL,
        pw_hash TEXT NOT NULL,
        role TEXT NOT NULL,        -- assistant/officer/leader/agency/supervisor
        display_name TEXT DEFAULT '',
        active INTEGER DEFAULT 1)""")

    c.execute("""CREATE TABLE IF NOT EXISTS projects(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        number TEXT UNIQUE,                 -- 项目编号（自动生成）
        name TEXT NOT NULL,                 -- 项目名称
        amount REAL,                        -- 金额（元）
        line TEXT,                          -- 流程线 A(<2万)/B(2-5万)/C(>=5万)
        method TEXT DEFAULT '',             -- 采购方式（议价/询价/代理等）
        demand_dept TEXT DEFAULT '',        -- 需求科室
        manage_dept TEXT DEFAULT '',        -- 归口管理科室
        agency_code TEXT DEFAULT '',        -- 代理机构缩写（C线用）
        officer TEXT DEFAULT '',            -- 项目经办人
        content TEXT DEFAULT '',            -- 包号及采购内容
        bid_time TEXT DEFAULT '',           -- 开标时间
        status TEXT DEFAULT '立项',         -- 当前状态
        supervisor TEXT DEFAULT '',         -- 监督人员
        representative TEXT DEFAULT '',     -- 采购人代表
        created_by TEXT DEFAULT '',
        created_at TEXT DEFAULT '',
        updated_at TEXT DEFAULT '')""")

    # 编号顺序号计数表：按 (类型, 年月) 记当前已用到的序号
    # kind: 'XJ'(<5万) 或 'JX'(>=5万)；ym: 2605 这种
    c.execute("""CREATE TABLE IF NOT EXISTS number_seq(
        kind TEXT NOT NULL,
        ym TEXT NOT NULL,
        seq INTEGER DEFAULT 0,
        PRIMARY KEY(kind, ym))""")

    # 预置代理机构
    for code, name in AGENCIES:
        c.execute("INSERT OR IGNORE INTO agencies(code,name) VALUES(?,?)", (code, name))
    # 预置监督人员
    for nm in SUPERVISORS:
        c.execute("INSERT OR IGNORE INTO people(name,role_type) VALUES(?, 'supervisor')", (nm,))
    # 预置用户
    for u, pw, role, dn in USERS:
        salt = secrets.token_hex(16)
        c.execute("""INSERT OR IGNORE INTO users(username,salt,pw_hash,role,display_name)
                     VALUES(?,?,?,?,?)""", (u, salt, hash_pw(pw, salt), role, dn))

    conn.commit()
    # 汇报
    print("[*] 数据库就绪:", DB)
    print("[*] 代理机构:", conn.execute("SELECT COUNT(*) FROM agencies").fetchone()[0], "家")
    print("[*] 监督人员:", [r[0] for r in conn.execute("SELECT name FROM people").fetchall()])
    print("[*] 用户账号:")
    for u, pw, role, dn in USERS:
        print(f"      {u} / {pw}  ({dn}, role={role})")
    print("[*] 现有项目:", conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
    conn.close()

if __name__ == "__main__":
    init()
