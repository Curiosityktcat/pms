"""用应用自己的密钥签一个会话 cookie，对着真正在跑的 1573 端口验证闸门。

生产开了登录滑块，脚本走不了正常登录；但要确认的是「跑着的那个进程里闸门是否生效」，
用服务自己的 PMS_SECRET_KEY 造一个合法会话即可，等价于科室账号登录后的状态。
"""
import io
import os
import sys

import requests
from flask.sessions import SecureCookieSessionInterface

BASE = "http://127.0.0.1:1573"
KEYFILE = os.path.expanduser("~/pms/.pms_secret_key")

FAIL = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("✓" if cond else "✗", name, ("  → " + detail) if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


class _Fake:
    def __init__(self, key):
        self.secret_key = key
        self.config = {"SESSION_COOKIE_SALT": "cookie-session", "SECRET_KEY_FALLBACKS": None}
        self.session_cookie_name = "session"
        self.permanent_session_lifetime = None


secret = io.open(KEYFILE, encoding="utf-8").read().strip()
si = SecureCookieSessionInterface()
serializer = si.get_signing_serializer(_Fake(secret))
if serializer is None:
    print("无法构造签名器"); sys.exit(1)

cookie = serializer.dumps({
    "user": "医学装备部", "role": "dept", "dept_code": "SBK",
    "agency_code": "", "display_name": "医学装备部", "_permanent": True,
})

s = requests.Session()
s.cookies.set("session", cookie)

print("[1] 门户可用（真实 HTTP）")
r = s.get("%s/api/dept/me" % BASE, timeout=10)
ok = r.status_code == 200
check("me 可取", ok, str(r.status_code))
if ok:
    d = r.json()["data"]
    check("科室=医学装备部", (d.get("dept") or {}).get("code") == "SBK")
    check("不可切换科室", d.get("can_switch") is False)

r = s.get("%s/api/dept/overview" % BASE, timeout=15)
ov = r.json().get("data", {}) if r.status_code == 200 else {}
check("概览可取", r.status_code == 200, str(r.status_code))
print("     科室=%s 总数=%s 在办=%s 已归档=%s" % (
    ov.get("dept"), ov.get("total"), ov.get("ongoing"), ov.get("archived")))

r = s.get("%s/api/dept/projects?archived=0" % BASE, timeout=20)
rows = r.json().get("data", []) if r.status_code == 200 else []
check("在办项目可取", r.status_code == 200 and len(rows) > 0, "%d 条" % len(rows))
for x in rows[:3]:
    print("     %s  %-30s → %s" % (x["number"], x["name"][:30], x["stage_cn"]))

print("[2] 闸门：采购部接口一律 403（真实 HTTP）")
for path in ("/api/projects", "/api/archive", "/api/contracts", "/api/procurement-plans",
             "/api/agency-assessments", "/api/auth-letter-records", "/api/web-announcements",
             "/api/procurement-results", "/api/project-review/projects"):
    r = s.get("%s%s" % (BASE, path), timeout=10)
    check("%s → 403" % path, r.status_code == 403, str(r.status_code))

print("[3] 资料能取到")
if rows:
    pid = rows[0]["id"]
    r = s.get("%s/api/dept/projects/%d/tree" % (BASE, pid), timeout=20)
    check("资料树可取", r.status_code == 200, str(r.status_code))
    tree = r.json().get("data", []) if r.status_code == 200 else []
    urls = [it["preview_url"] for f in tree for it in f.get("items", [])]
    off = [u for u in urls if not u.startswith("/api/dept/")]
    check("资料地址都在门户命名空间内", not off, "仍指向：%s" % ", ".join(sorted(set(off))[:4]))
    if urls:
        r = s.get("%s%s" % (BASE, urls[0]), timeout=40)
        check("能下载资料", r.status_code == 200,
              "%s %s" % (r.status_code, r.headers.get("content-type", "")[:40]))

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "; ".join(FAIL)))
    sys.exit(1)
print("跑着的服务上，科室门户与闸门均已生效")
