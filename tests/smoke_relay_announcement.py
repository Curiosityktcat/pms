# -*- coding: utf-8 -*-
"""第二个模块验证：公告附件（AnnouncementPage / 更正公告 / 调研公示 三个页面共用这个口）。"""
import io, os, sys, time, sqlite3
sys.path.insert(0, os.path.expanduser("~/pms/backend"))
os.chdir(os.path.expanduser("~/pms/backend"))
import requests
from flask.sessions import SecureCookieSessionInterface
from flask import Flask

SECRET = io.open("/home/huangxb/pms/.pms_secret_key", encoding="utf-8").read().strip()
app = Flask(__name__); app.secret_key = SECRET
ck = SecureCookieSessionInterface().get_signing_serializer(app).dumps(
    {"user": "黄新博", "role": "officer", "display_name": "黄新博"})
s = requests.Session(); s.cookies.set("session", ck)
PUB = "https://pms.curiosityktcat.cn"
LAN = "http://127.0.0.1:1573"
MB = 40

c = sqlite3.connect("/home/huangxb/pms/pms.db")
cols = [r[1] for r in c.execute("PRAGMA table_info(announcements)")]
aid = int(sys.argv[1]) if len(sys.argv)>1 else c.execute("select id from announcements order by id desc limit 1").fetchone()[0]
print(f"目标公告 id={aid}")

ok = fail = 0
def check(n, cond, e=""):
    global ok, fail
    if cond: ok += 1; print(f"  [通过] {n} {e}")
    else: fail += 1; print(f"  [失败] {n} {e}")

p = "/home/huangxb/.cache/relay_ann.pdf"
if not os.path.exists(p) or os.path.getsize(p) != MB * 1024 * 1024:
    with open(p, "wb") as f:
        f.write(b"%PDF-1.4\n"); f.write(b"E" * (MB * 1024 * 1024 - 9))

before = s.get(f"{LAN}/api/announcements/{aid}/files", timeout=60).json().get("data") or []

r = s.post(f"{PUB}/api/storage/sign-upload",
           json={"module": "staging", "filename": "传输测试_公告_可删除.pdf"}, timeout=120)
d = r.json(); check("签名 direct", d.get("direct"), str(d)[:80])
f0 = d["form"]
t0 = time.time()
with open(p, "rb") as fh:
    rr = requests.post(f0["host"],
                       data={k: f0[k] for k in ("key", "policy", "OSSAccessKeyId", "signature")},
                       files={"file": ("传输测试_公告_可删除.pdf", fh, "application/pdf")}, timeout=900)
check("OSS 直传 204", rr.status_code == 204, f"{time.time()-t0:.1f}s")

t1 = time.time()
r = s.post(f"{PUB}/api/announcements/{aid}/files",
           data={"oss_key": d["rel_path"], "original_name": "传输测试_公告_可删除.pdf"}, timeout=300)
check("公告附件接口 200/201", r.status_code in (200, 201),
      f"HTTP {r.status_code} {time.time()-t1:.1f}s {r.text[:140]}")

after = s.get(f"{LAN}/api/announcements/{aid}/files", timeout=60).json().get("data") or []
new = [x for x in after if x["id"] not in {y["id"] for y in before}]
check("附件已入库", len(new) == 1, f"新增 {len(new)} 条")
if new:
    fid = new[0]["id"]
    sz = new[0].get("file_size")
    check("大小与原文件一致", sz == MB * 1024 * 1024, f"{sz} B")
    rd = s.get(f"{LAN}/api/announcements/{aid}/files/{fid}", stream=True, timeout=300)
    n = sum(len(x) for x in rd.iter_content(1024 * 1024))
    check("下载字节一致", rd.status_code == 200 and n == MB * 1024 * 1024, f"{n} B")
    dr = s.delete(f"{LAN}/api/announcements/{aid}/files/{fid}", timeout=60)
    check("测试附件已删除", dr.status_code in (200, 204), f"HTTP {dr.status_code}")

from services import storage
check("暂存对象已清理", not storage.exists(d["rel_path"]))
try: os.remove(p)
except OSError: pass
print(f"\n结果：通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
