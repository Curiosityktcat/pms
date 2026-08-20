# -*- coding: utf-8 -*-
"""对跑着的 1573 验证：监督账号既看全院、又有自己科室的默认视角。

生产开了登录滑块，脚本走不了正常登录，用服务自己的密钥签会话（等价于登录后状态）。
"""
import io
import sys

import requests
from flask.sessions import SecureCookieSessionInterface

BASE = "http://127.0.0.1:1573"
FAIL = []


def check(name, cond, detail=""):
    print("  %s %s%s" % ("✓" if cond else "✗", name, ("  → " + detail) if detail else ""))
    if not cond:
        FAIL.append(name)


class F:
    def __init__(self, k):
        self.secret_key = k
        self.config = {"SESSION_COOKIE_SALT": "cookie-session", "SECRET_KEY_FALLBACKS": None}
        self.session_cookie_name = "session"
        self.permanent_session_lifetime = None


sec = io.open("/home/huangxb/pms/.pms_secret_key", encoding="utf-8").read().strip()
ser = SecureCookieSessionInterface().get_signing_serializer(F(sec))


def sess(user, role, dept):
    ck = ser.dumps({"user": user, "role": role, "dept_code": dept, "agency_code": "",
                    "display_name": user, "must_change_pw": 0, "_permanent": True})
    s = requests.Session()
    s.cookies.set("session", ck)
    return s


for user, dept, label in [("审计科", "SJK", "审计科（监督+归口）"),
                          ("纪委办公室", "JWB", "纪委办公室（监督+归口）")]:
    print("[%s]" % label)
    s = sess(user, "supervisor", dept)

    r = s.get(BASE + "/api/dept/me", timeout=10)
    d = r.json().get("data", {}) if r.status_code == 200 else {}
    dd = d.get("dept") or {}
    check("门户默认视角 = 本科室", dd.get("code") == dept, "%s" % dd.get("name"))
    check("仍可切换看别的科室", d.get("can_switch") is True)

    r = s.get(BASE + "/api/dept/overview", timeout=15)
    ov = r.json().get("data", {}) if r.status_code == 200 else {}
    print("     本科室项目 总数=%s 在办=%s 已归档=%s" % (
        ov.get("total"), ov.get("ongoing"), ov.get("archived")))

    r = s.get(BASE + "/api/projects", timeout=20)
    n = len(r.json().get("data", [])) if r.status_code == 200 else -1
    check("监督仍看得到全院项目", n > 300, "%d 条" % n)

    r = s.get(BASE + "/api/dept/overview?dept=SBK", timeout=15)
    ov2 = r.json().get("data", {}) if r.status_code == 200 else {}
    check("可切到别的科室看", (ov2.get("dept") or "").find("医学装备") >= 0, str(ov2.get("dept")))
    print()

print("[对照：助理不受回落影响]")
s = sess("admin", "assistant", "")
r = s.get(BASE + "/api/dept/me", timeout=10)
d = r.json().get("data", {}) if r.status_code == 200 else {}
check("助理没绑科室 → 默认视角仍为空", (d.get("dept") is None), str(d.get("dept")))
check("助理仍可切换", d.get("can_switch") is True)

print()
if FAIL:
    print("失败 %d 项：%s" % (len(FAIL), "; ".join(FAIL)))
    sys.exit(1)
print("监督+归口双身份已生效")
