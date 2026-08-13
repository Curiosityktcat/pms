# -*- coding: utf-8 -*-
"""从正式库做一份一致的测试库副本。

不能用 cp：pms.db 是 WAL 模式，正式服还在写。cp 只拷主文件、拉不到 -wal 里
还没归并的那部分，拷出来的库大概率是坏的（"database disk image is malformed"），
测试实例连启动都启动不了。SQLite 的在线备份接口会给一个一致快照，
拷完再校验一次完整性——校验不过就不覆盖，宁可不换也别拿坏库开工。

正式库只以只读方式打开，一个字节都不写。
"""
import os
import sqlite3
import sys

ROOT = os.path.expanduser("~/pms")
SRC = os.path.join(ROOT, "pms.db")
DST = os.path.join(ROOT, "pms.test.db")
TMP = DST + ".new"

if os.path.exists(TMP):
    os.remove(TMP)

src = sqlite3.connect("file:%s?mode=ro" % SRC, uri=True)
dst = sqlite3.connect(TMP)
src.backup(dst)
dst.close()
src.close()

chk = sqlite3.connect(TMP)
res = chk.execute("pragma integrity_check").fetchone()[0]
n = chk.execute("select count(*) from projects").fetchone()[0]
chk.close()
print("完整性校验:", res)
print("项目数:", n)
if res != "ok":
    print("校验没过，不覆盖测试库")
    sys.exit(1)
os.replace(TMP, DST)
for ext in ("-wal", "-shm"):
    p = DST + ext
    if os.path.exists(p):
        os.remove(p)          # 旧的 WAL 配不上新主库，留着会读到错的东西
print("已替换 ->", DST)
