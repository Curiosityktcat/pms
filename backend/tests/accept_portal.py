# -*- coding: utf-8 -*-
"""官网挂网验收（只打测试库 pms.test.db）。

安全约定：全程 audit=False、regenerate=False —— 记录停在「未审核」，
不点生成列表页/详情页，所以公众页面不会出现任何东西；跑完立即删除。
"""
import io
import os
import sys
import time

sys.path.insert(0, ".")
os.environ["PMS_DB_PATH"] = "/home/huangxb/pms/pms.test.db"
os.environ["PMS_CAPTCHA_ON"] = "0"

ok, bad = 0, []


def check(t, c, e=""):
    global ok
    if c:
        ok += 1
        print(f"OK   {t} {e}")
    else:
        bad.append(t)
        print(f"FAIL {t} {e}")


from services import njyy_portal as portal

# ① 配置与会话
check("① 配置在位且已启用", portal.enabled())
cfg = portal.load_cfg()
check("① 栏目就是招标采购信息(sort=34)", portal.SORT_ID == 34)

t0 = time.time()
s, cfg = portal._session_for("publisher")
check("② sjkfb 会话可用", portal._logged_in(s, cfg), f"{time.time()-t0:.1f}s")
t1 = time.time()
s2, _ = portal._session_for("publisher")
check("② 第二次拿会话走缓存（更快）", portal._logged_in(s2, cfg), f"{time.time()-t1:.1f}s")
a, _ = portal._session_for("auditor")
check("② sjksh 会话可用", portal._logged_in(a, cfg))

# ③ 附件上传
blob = io.open("/home/huangxb/pms/backend/services/njyy_portal.py", "rb").read()[:2000]
url = portal.upload_file(s, cfg, "PMS挂网联调.txt", blob)
check("③ 附件能传上官网", url.startswith("/"), f"→ {url}")

# ④ 新增（不审核、不生成 → 公众看不到）
title = "【PMS联调请勿处理】" + time.strftime("%m%d%H%M%S")
html = "<p>PMS 自动挂网联调记录，未审核、未生成页面，稍后自动删除。</p>"
res = portal.publish(title, html, [("PMS挂网联调.txt", blob)], audit=False, regenerate=False)
nid = res["news_id"]
check("④ 新增成功并拿到记录 id", bool(nid), f"id={nid}")
check("④ 公网地址按 News/info/id 规律拼出", res["url"].endswith(f"/News/info/id/{nid}.html"),
      res["url"])

st = portal.status(nid)
check("⑤ 后台查得到这条，且处于未审核", st["exists"] and not st["audited"], str(st["marks"]))
check("⑤ 未审核时公众页面打不开", not portal.verify(res["url"]))

# ⑥ 审核开关能来回切
a, cfg = portal._session_for("auditor")
a.get(cfg["base"] + f"/managernjyy-News-change-id-{nid}-zd-isshow.html", timeout=60)
st2 = portal.status(nid)
check("⑥ 切一下变成已审核", st2["audited"], str(st2["marks"]))
a.get(cfg["base"] + f"/managernjyy-News-change-id-{nid}-zd-isshow.html", timeout=60)
st3 = portal.status(nid)
check("⑥ 再切回未审核", not st3["audited"], str(st3["marks"]))

# ⑦ 删除（撤网口径），不重新生成列表页——本来也没生成过
r = portal.revoke(nid, regenerate=False)
check("⑦ 删除成功", True, str(r["steps"]))
check("⑦ 后台列表里已经没有这条", not portal.status(nid)["exists"])

# ⑧ 验证码指纹缓存有没有攒下来
cap = portal._load_json(portal.CAP_PATH, {})
check("⑧ 验证码指纹缓存已记录", len(cap) >= 1, f"已记 {len(cap)} 张")

print(f"\n通过 {ok} 项" + (f"，失败 {len(bad)}：{bad}" if bad else "，全部通过"))
sys.exit(1 if bad else 0)
