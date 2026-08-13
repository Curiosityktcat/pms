# -*- coding: utf-8 -*-
"""OSS 中转上传端到端实测：完整模拟浏览器行为，走公网域名。

流程：签暂存策略 → 直传 OSS → 业务接口凭 oss_key 取回 → 校验落盘 → 删附件收尾。
"""
import io, os, sys, time
sys.path.insert(0, os.path.expanduser("~/pms/backend"))
os.chdir(os.path.expanduser("~/pms/backend"))
import requests
from flask.sessions import SecureCookieSessionInterface
from flask import Flask

app = Flask(__name__)
SECRET = io.open("/home/huangxb/pms/.pms_secret_key", encoding="utf-8").read().strip()
app.secret_key = SECRET
ck = SecureCookieSessionInterface().get_signing_serializer(app).dumps(
    {"user": "黄新博", "role": "officer", "display_name": "黄新博"})

PUB = "https://pms.curiosityktcat.cn"
LAN = "http://127.0.0.1:1573"
CID = int(sys.argv[1]) if len(sys.argv) > 1 else 19
MB = 40

ok = fail = 0
def check(n, c, e=""):
    global ok, fail
    if c: ok += 1; print(f"  [通过] {n} {e}")
    else: fail += 1; print(f"  [失败] {n} {e}")

p = "/home/huangxb/.cache/relay40.pdf"
if not os.path.exists(p) or os.path.getsize(p) != MB * 1024 * 1024:
    with open(p, "wb") as f:
        f.write(b"%PDF-1.4\n")
        f.write(b"C" * (MB * 1024 * 1024 - 9))

s = requests.Session(); s.cookies.set("session", ck)

print(f"=== 1. 公网签暂存策略（合同 {CID}）===")
t0 = time.time()
r = s.post(f"{PUB}/api/storage/sign-upload",
           json={"module": "staging", "filename": "传输测试_可删除.pdf"}, timeout=120)
d = r.json()
check("签名 200 且 direct=true", r.status_code == 200 and d.get("direct"),
      f"HTTP {r.status_code} {str(d)[:120]}")
if not d.get("direct"):
    sys.exit("拿不到直传策略")
rel = d["rel_path"]
check("暂存路径落在本人专属暂存区", rel.startswith("uploads/_staging/"), rel)

print("=== 2. 直传 OSS（绕开 Cloudflare）===")
f0 = d["form"]
t1 = time.time()
with open(p, "rb") as fh:
    rr = requests.post(f0["host"],
                       data={k: f0[k] for k in ("key", "policy", "OSSAccessKeyId", "signature")},
                       files={"file": ("传输测试_可删除.pdf", fh, "application/pdf")},
                       timeout=900)
dt_oss = time.time() - t1
check("OSS 直传 204", rr.status_code == 204, f"{dt_oss:.1f}s  {MB/dt_oss:.2f} MB/s")

print("=== 3. 业务接口凭 oss_key 取回（公网，只传几百字节）===")
t2 = time.time()
r = s.post(f"{PUB}/api/contracts/{CID}/attachments",
           data={"oss_key": rel, "original_name": "传输测试_可删除.pdf", "stage": "上传"},
           timeout=300)
dt_reg = time.time() - t2
check("业务接口 200", r.status_code == 200, f"HTTP {r.status_code} {dt_reg:.1f}s {r.text[:160]}")
att = (r.json().get("data") or {}) if r.status_code == 200 else {}
aid = att.get("id")
check("库里记的大小与原文件一致",
      att.get("file_size") == MB * 1024 * 1024, f"{att.get('file_size')} B")
check("原始文件名保留", att.get("original_name") == "传输测试_可删除.pdf", str(att.get("original_name")))

local = os.path.abspath(os.path.join("..", "uploads", "contracts", str(CID), "attachments", att.get("saved_name") or "_"))
check("文件真落到本地原路径（下载/预览/rd-web 推送才读得到）",
      os.path.exists(local) and os.path.getsize(local) == MB * 1024 * 1024,
      local if os.path.exists(local) else "不存在")

print("=== 4. 暂存对象已被清理（不留垃圾、不重复计费）===")
from services import storage
check("OSS 暂存区对象已删", not storage.exists(rel), rel)

print("=== 5. 下载仍走原路径（附件读取未受影响）===")
if aid:
    r = s.get(f"{LAN}/api/contracts/{CID}/attachments/{aid}/download", stream=True, timeout=300)
    n = sum(len(c) for c in r.iter_content(1024 * 1024))
    check("下载 200 且字节一致", r.status_code == 200 and n == MB * 1024 * 1024, f"{n} B")

print("=== 6. 越权保护：拿别人的暂存键认领不了 ===")
import hmac, hashlib
other = hmac.new(SECRET.encode(), b"staging:\xe9\x83\x91\xe8\xb7\x83\xe4\xbf\x8a", hashlib.sha256).hexdigest()[:16]
r = s.post(f"{LAN}/api/contracts/{CID}/attachments",
           data={"oss_key": f"uploads/_staging/{other}/x_y_z.pdf",
                 "original_name": "别人的.pdf", "stage": "上传"}, timeout=60)
check("他人暂存键被拒（400 未选择文件）", r.status_code == 400, f"HTTP {r.status_code} {r.text[:80]}")

print("=== 7. 局域网老路不受影响（普通 multipart）===")
small = "/home/huangxb/.cache/relay_small.pdf"
with open(small, "wb") as f:
    f.write(b"%PDF-1.4\n" + b"D" * 200000)
with open(small, "rb") as fh:
    r = s.post(f"{LAN}/api/contracts/{CID}/attachments",
               data={"stage": "上传"},
               files={"file": ("传输测试_小文件_可删除.pdf", fh, "application/pdf")}, timeout=120)
check("普通 multipart 仍 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:100]}")
aid2 = (r.json().get("data") or {}).get("id") if r.status_code == 200 else None

print("=== 8. 清理测试附件 ===")
for a in [x for x in (aid, aid2) if x]:
    rr = s.delete(f"{LAN}/api/contracts/{CID}/attachments/{a}", timeout=60)
    print(f"    删附件 {a}: HTTP {rr.status_code}")
r = s.get(f"{LAN}/api/contracts/{CID}/attachments", timeout=60)
left = [x for x in (r.json().get("data") or []) if "传输测试" in (x.get("original_name") or "")]
check("测试附件已清干净", not left, f"残留 {len(left)} 条")
for q in (p, small):
    try: os.remove(q)
    except OSError: pass

print(f"\n公网整体耗时：签名+直传 {dt_oss:.1f}s + 取回 {dt_reg:.1f}s（改造前：131s 后 524 失败）")
print(f"结果：通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
