# -*- coding: utf-8 -*-
"""内网传输回归：真实 HTTP 打 127.0.0.1:1573。

会话 cookie 用 PMS 自己的 SECRET_KEY 现签（等价于用黄新博账号登录），
测完把测试目录删干净。
"""
import io, os, sys, time, json

sys.path.insert(0, os.path.expanduser("~/pms/backend"))
import requests
from flask.sessions import SecureCookieSessionInterface
from flask import Flask

SECRET = io.open("/home/huangxb/pms/.pms_secret_key", encoding="utf-8").read().strip()
BASE = "http://127.0.0.1:1573"
TESTDIR = "_传输回归测试"
SIZE = 291 * 1024 * 1024
TMP = "/home/huangxb/.cache/tf_291mb.bin"

app = Flask(__name__)
app.secret_key = SECRET
si = SecureCookieSessionInterface()
s = si.get_signing_serializer(app)
cookie = s.dumps({"user": "黄新博", "role": "officer"})

sess = requests.Session()
sess.cookies.set("session", cookie)

ok = fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  [通过] {name} {extra}")
    else:
        fail += 1; print(f"  [失败] {name} {extra}")

print("=== 0. 会话可用性 ===")
r = sess.get(f"{BASE}/api/filebox/list", params={"path": ""}, timeout=30)
check("列目录 200", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code != 200:
    sys.exit("会话无效，后续测试无意义：" + r.text[:200])

sess.post(f"{BASE}/api/filebox/mkdir", json={"path": "", "name": TESTDIR}, timeout=30)

print("=== 1. 291MB 真实上传（复现原故障场景）===")
if not os.path.exists(TMP) or os.path.getsize(TMP) != SIZE:
    with open(TMP, "wb") as f:
        chunk = os.urandom(1024 * 1024)
        for _ in range(291):
            f.write(chunk)
t0 = time.time()
with open(TMP, "rb") as fh:
    r = sess.post(f"{BASE}/api/filebox/upload",
                  data={"path": TESTDIR},
                  files={"file": ("大文件291mb.bin", fh, "application/octet-stream")},
                  timeout=600)
dt = time.time() - t0
body = r.text[:200]
check("上传 200", r.status_code == 200, f"HTTP {r.status_code} 耗时{dt:.1f}s {body}")
dst = os.path.expanduser(f"~/files/{TESTDIR}/大文件291mb.bin")
check("文件真落盘且大小一致", os.path.exists(dst) and os.path.getsize(dst) == SIZE,
      f"{os.path.getsize(dst) if os.path.exists(dst) else 0} B")

print("=== 2. 截断上传 → 报错要说人话（原来指向 Cloudflare）===")
import socket
boundary = "----RegressBoundary"
head = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"path\"\r\n\r\n{TESTDIR}\r\n"
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"trunc.bin\"\r\n"
        f"Content-Type: application/octet-stream\r\n\r\n").encode()
declared = 200 * 1024 * 1024
c = socket.create_connection(("127.0.0.1", 1573), timeout=30)
req = (f"POST /api/filebox/upload HTTP/1.1\r\nHost: 127.0.0.1:1573\r\n"
       f"Cookie: session={cookie}\r\n"
       f"Content-Type: multipart/form-data; boundary={boundary}\r\n"
       f"Content-Length: {declared}\r\nConnection: close\r\n\r\n").encode()
c.sendall(req + head + b"X" * (1024 * 1024))   # 只发 1MB 就停（模拟浏览器 abort）
c.shutdown(socket.SHUT_WR)
resp = b""
try:
    while True:
        b = c.recv(65536)
        if not b: break
        resp += b
except Exception:
    pass
c.close()
text = resp.decode("utf-8", "replace")
_body = text.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in text else text
try:
    _msg = json.loads(_body).get("error", "")   # jsonify 会把中文转成 \uXXXX，必须解码后再比对
except Exception:
    _msg = _body
check("截断返回 400", " 400 " in text.split("\r\n")[0], text.split("\r\n")[0])
check("提示已改成「上传中途被中断」", "上传中途被中断" in _msg, _msg[:60])
check("提示不再把内网问题甩给 Cloudflare 优先", "请求体已传输但未解析到文件" not in _msg)

print("=== 3. 大文件原生下载（浏览器直链，不经 blob）===")
t0 = time.time()
r = sess.get(f"{BASE}/api/filebox/download",
             params={"path": f"{TESTDIR}/大文件291mb.bin"}, stream=True, timeout=600)
n = sum(len(ch) for ch in r.iter_content(1024 * 1024))
dt = time.time() - t0
check("下载 200 且字节数一致", r.status_code == 200 and n == SIZE,
      f"{n} B / {dt:.1f}s = {n/dt/1048576:.0f} MB/s")
check("带 Content-Disposition（浏览器才会存盘）",
      "attachment" in (r.headers.get("Content-Disposition") or ""),
      r.headers.get("Content-Disposition", "")[:60])

print("=== 4. 文件夹打包下载 ===")
r = sess.get(f"{BASE}/api/filebox/download-folder", params={"path": TESTDIR},
             stream=True, timeout=600)
n = sum(len(ch) for ch in r.iter_content(1024 * 1024))
check("zip 200 且有内容", r.status_code == 200 and n > 0, f"{n/1048576:.0f} MB")

print("=== 5. doc-intake 反代改流式后仍通 ===")
r = sess.get(f"{BASE}/doc-intake-svc/", timeout=60)
check("反代 GET 200", r.status_code == 200, f"HTTP {r.status_code}")
r = sess.post(f"{BASE}/doc-intake-svc/classify",
              json={"text": "四川省人民医院采购合同 项目编号 NJYYJX-CJ-2605001 合同金额 12 万元"},
              timeout=300)
check("反代 POST（流式转发）200", r.status_code == 200,
      f"HTTP {r.status_code} {r.text[:120]}")

print("=== 6. 牛马 agent 反代仍通 ===")
r = sess.get(f"{BASE}/officer-agent/healthz", timeout=60)
check("officer 反代 GET", r.status_code in (200, 404), f"HTTP {r.status_code} {r.text[:80]}")

print("=== 7. 清理 ===")
r = sess.post(f"{BASE}/api/filebox/delete", json={"path": TESTDIR}, timeout=60)
check("测试目录已删除", r.status_code == 200 and not os.path.exists(os.path.expanduser(f"~/files/{TESTDIR}")))
try: os.remove(TMP)
except OSError: pass

print(f"\n结果：通过 {ok} / 失败 {fail}")
sys.exit(1 if fail else 0)
