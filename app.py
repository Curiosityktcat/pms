#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
采购项目管理系统 - 第1阶段 v3
本次范围：左侧导航框架(10模块,多数占位) + 项目立项 + 项目流程(列表)
含：采购方式按金额自动带出/仅可改单一来源、招单价、单一来源走代理、草稿、删除、金额+元、代理全称
运行：python app.py   依赖：flask
"""
import os, sqlite3, hashlib, datetime, json as _json
from functools import wraps
from flask import (Flask, request, redirect, url_for, session,
                   render_template_string, flash, g)
import numbering as N

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "pms.db")
app = Flask(__name__)
app.secret_key = "change-this-secret-key-please"
PORT = 8081

STATUSES = ["立项","委托代理","编制中","审核中","已发公告","报名中","开标","已定标","合同签订","已归档"]
ROLE_CN = {"assistant":"采购部助理","officer":"项目经办人","leader":"采购部负责人","agency":"代理机构","supervisor":"监督"}
METHODS = [N.M_YIJIA, N.M_XUNJIA, N.M_JINGXUAN, N.M_SOLE]
METHOD_HINT = {
    N.M_YIJIA:"2万以下的货物/工程/服务",
    N.M_XUNJIA:"2万(含)~5万",
    N.M_JINGXUAN:"5万(含)以上，需指派代理机构",
    N.M_SOLE:"需专家论证+公示；可走可不走代理（下方选择）",
}

# 左侧导航：(模块key, 名称, [子项(key,名称,是否可用)])  available=True 才能点
NAV = [
    ("req","采购需求审签",[("req_make","采购需求编制",False),("req_node","审签节点查看",False)]),
    ("dispatch","采购项目分发",[]),
    ("agreement","代理协议",[]),
    ("pm","采购项目管理",[("pm_new","项目立项",True),("pm_flow","项目流程",True),
                          ("pm_bid","开标管理",True),("pm_auth","授权函",False)]),
    ("doc","采购文件编制",[]),
    ("publish","挂网管理",[("pub_gg","采购公告",False),("pub_dy","调研公告",False),
                          ("pub_gz","更正公告",False),("pub_dy2","单一来源公示",False),("pub_xj","询/议价函",False)]),
    ("review","项目评审",[("rv_bm","供应商报名",False),("rv_pd","评定表报告",False),("rv_online","在线评审",False)]),
    ("result","采购结果确认",[]),
    ("contract","合同管理",[]),
    ("archive","归档",[]),
]

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB); g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db: db.close()

def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()

def agency_name(code):
    if not code: return ""
    r = get_db().execute("SELECT name FROM agencies WHERE code=?", (code,)).fetchone()
    return r["name"] if r else code

def login_required(f):
    @wraps(f)
    def w(*a, **k):
        if "user" not in session: return redirect(url_for("login"))
        return f(*a, **k)
    return w

# ---------- 布局：左侧导航 + 右侧内容 ----------
LAYOUT = """
<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>采购项目管理</title><style>
*{box-sizing:border-box}body{font-family:'Microsoft YaHei',sans-serif;margin:0;background:#eef1f4;color:#333}
.layout{display:flex;min-height:100vh}
.side{width:230px;background:#1f2d3d;color:#cdd6e0;flex-shrink:0;overflow-y:auto}
.side .brand{padding:16px 18px;font-weight:bold;color:#fff;font-size:16px;border-bottom:1px solid #2c3e50}
.side .grp{padding:0}
.side .g-title{padding:11px 18px;color:#8fa3b8;font-size:14px;cursor:default}
.side a{display:block;padding:9px 18px 9px 34px;color:#cdd6e0;text-decoration:none;font-size:13.5px}
.side a:hover{background:#2c3e50}
.side a.active{background:#2980b9;color:#fff}
.side a.disabled{color:#5d6b7a;cursor:not-allowed}
.side a.top1{padding-left:18px;font-weight:bold;color:#dfe7ee}
.main{flex:1;display:flex;flex-direction:column}
.topbar{background:#fff;padding:12px 24px;display:flex;align-items:center;border-bottom:1px solid #e3e8ee}
.topbar .sp{margin-left:auto;font-size:14px;color:#555}
.topbar a{color:#2980b9;text-decoration:none}
.content{padding:22px;flex:1}
.card{background:#fff;border-radius:8px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.06);margin-bottom:18px}
h2{color:#2c3e50;margin-top:0}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{border-bottom:1px solid #eee;padding:9px 10px;text-align:left}
th{background:#34495e;color:#fff}tr:hover{background:#f7fbff}
input,select,textarea{padding:8px;border:1px solid #ccc;border-radius:5px;font-size:14px}
label{display:block;margin:10px 0 4px;font-size:14px;color:#555}
.btn{background:#2980b9;color:#fff;border:0;padding:9px 20px;border-radius:6px;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block}
.btn.gray{background:#95a5a6}.btn.sm{padding:4px 12px;font-size:13px}.btn.red{background:#c0392b}
.row{display:flex;gap:16px;flex-wrap:wrap}.row>div{flex:1;min-width:200px}
.flash{background:#fdf0e6;border:1px solid #e67e22;color:#d35400;padding:10px;border-radius:6px;margin-bottom:14px}
.hint{color:#888;font-size:12px;margin-top:2px}
a.proj{color:#2980b9;text-decoration:none;font-weight:bold}
.tag{padding:2px 8px;border-radius:4px;font-size:12px;background:#ecf0f1;color:#555}
.tag.draft{background:#f39c12;color:#fff}
.dev{color:#888;text-align:center;padding:60px}
</style></head><body>
<div class="layout">
<div class="side">
  <div class="brand">🏥 采购项目管理</div>
  {% for key,name,subs in NAV %}
    {% if subs %}
      <div class="g-title">{{name}}</div>
      {% for sk,sn,av in subs %}
        {% if av %}<a class="{{'active' if active==sk}}" href="{{url_for('page', mod=sk)}}">{{sn}}</a>
        {% else %}<a class="disabled" title="开发中">{{sn}}（开发中）</a>{% endif %}
      {% endfor %}
    {% else %}
      <a class="top1 disabled" title="开发中">{{name}}（开发中）</a>
    {% endif %}
  {% endfor %}
</div>
<div class="main">
  <div class="topbar"><b>{{page_title or ''}}</b>
    <span class="sp">{{session.display_name}}（{{ROLE_CN.get(session.role,session.role)}}） · <a href="{{url_for('chpwd')}}">改密码</a> · <a href="{{url_for('logout')}}">退出</a></span>
  </div>
  <div class="content">
    {% with msgs = get_flashed_messages() %}{% if msgs %}{% for m in msgs %}<div class="flash">{{m}}</div>{% endfor %}{% endif %}{% endwith %}
    {{ body|safe }}
  </div>
</div></div></body></html>
"""

def render(body, active="", page_title="", **kw):
    inner = render_template_string(body, ROLE_CN=ROLE_CN, NAV=NAV, **kw)
    return render_template_string(LAYOUT, body=inner, active=active, page_title=page_title,
                                  ROLE_CN=ROLE_CN, NAV=NAV, **kw)

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form.get("username","").strip(); pw=request.form.get("password","")
        row=get_db().execute("SELECT * FROM users WHERE username=? AND active=1",(u,)).fetchone()
        if row and hash_pw(pw,row["salt"])==row["pw_hash"]:
            session["user"]=u; session["role"]=row["role"]; session["display_name"]=row["display_name"]
            session["agency_code"]=row["agency_code"] if "agency_code" in row.keys() else ""
            return redirect(url_for("page", mod="pm_flow"))
        flash("用户名或密码错误")
    body="""<div style="max-width:340px;margin:8% auto;background:#fff;padding:30px;border-radius:10px;box-shadow:0 2px 12px rgba(0,0,0,.1)">
    <h2 style="text-align:center;color:#2c3e50">🏥 采购项目管理</h2>
    <form method="post"><label>用户名</label><input name="username" style="width:100%" autofocus>
    <label>密码</label><input name="password" type="password" style="width:100%">
    <div style="margin-top:16px"><button class="btn" style="width:100%">登 录</button></div></form></div>"""
    msg="".join(f'<div class="flash">{m}</div>' for m in [])
    return render_template_string("<!doctype html><meta charset=utf-8><title>登录</title>"
        "<style>body{font-family:'Microsoft YaHei';background:#eef1f4}"
        ".btn{background:#2980b9;color:#fff;border:0;padding:10px;border-radius:6px;cursor:pointer}"
        "input{padding:9px;border:1px solid #ccc;border-radius:5px;margin-bottom:8px}label{display:block;margin:8px 0 3px}</style>"
        + "{% with m=get_flashed_messages() %}{% if m %}<div style='max-width:340px;margin:20px auto;color:#c0392b;text-align:center'>{{m[0]}}</div>{% endif %}{% endwith %}"
        + body)

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("login"))

# ---------- 统一页面路由 ----------
@app.route("/")
@login_required
def home():
    return redirect(url_for("page", mod="pm_flow"))

@app.route("/m/<mod>")
@login_required
def page(mod):
    if mod=="pm_flow":   return project_flow()
    if mod=="pm_new":    return redirect(url_for("new_project"))
    if mod=="pm_bid":    return bid_manage()
    # 其它都是占位
    title = "功能模块"
    for _,_,subs in NAV:
        for sk,sn,av in subs:
            if sk==mod: title=sn
    body=f'<div class="card"><div class="dev">🚧 「{title}」模块开发中，敬请期待</div></div>'
    return render(body, active=mod, page_title=title)

# ---------- 项目流程（列表）----------
def project_flow():
    db = get_db()
    if session.get("role")=="agency":
        # 代理机构：只看自己 agency_code 的项目（且不看草稿）
        rows = db.execute("SELECT * FROM projects WHERE agency_code=? AND COALESCE(is_draft,0)=0 ORDER BY id DESC",
                          (session.get("agency_code",""),)).fetchall()
    else:
        rows = db.execute("SELECT * FROM projects ORDER BY COALESCE(is_draft,0) DESC, id DESC").fetchall()
    body = """<div class="card"><h2>项目流程 <span style="font-size:14px;color:#888">（共 {{rows|length}} 个）</span>
      <a class="btn" style="float:right" href="{{url_for('new_project')}}">+ 项目立项</a></h2>
    <table><tr><th>编号</th><th>项目名称</th><th>预算金额</th><th>采购方式</th><th>代理机构</th>
      <th>经办人</th><th>状态</th><th>开标时间</th><th>操作</th></tr>
    {% for p in rows %}<tr>
      <td>{% if p['is_draft'] %}<span class="tag draft">草稿</span>{% else %}
          <a class="proj" href="{{url_for('edit_project', pid=p['id'])}}">{{p['number']}}</a>{% endif %}</td>
      <td><a class="proj" style="color:#333" href="{{url_for('edit_project', pid=p['id'])}}">{{p['name']}}</a></td>
      <td>{% if p['amount'] and p['amount']>0 %}{{'%.0f'|format(p['amount'])}} 元{% else %}招单价{% endif %}</td>
      <td>{{p['method']}}</td>
      <td>{{ag(p['agency_code'])}}</td>
      <td>{{p['officer']}}</td><td>{{p['status']}}</td><td>{{p['bid_time']}}</td>
      <td>
        <a class="btn sm" href="{{url_for('edit_project', pid=p['id'])}}">编辑</a>
        <a class="btn sm red" href="{{url_for('del_project', pid=p['id'])}}"
           onclick="return confirm('确定删除该项目？不可恢复')">删除</a>
      </td>
    </tr>{% else %}<tr><td colspan="9" style="text-align:center;color:#999;padding:24px">还没有项目</td></tr>{% endfor %}
    </table></div>"""
    return render(body, active="pm_flow", page_title="项目流程", rows=rows, ag=agency_name)

def _has_col(col):
    cols=[r["name"] for r in get_db().execute("PRAGMA table_info(projects)").fetchall()]
    return col in cols

# ---------- 立项 / 编辑 ----------
def _read_form(form):
    return {
        "name":form.get("name","").strip(),
        "amount_raw":form.get("amount","").strip(),
        "is_unit_price":form.get("is_unit_price")=="on",
        "method":form.get("method","").strip(),
        "sole_use_agency":form.get("sole_use_agency",""),
        "agency_code":form.get("agency_code","").strip(),
        "demand_dept":form.get("demand_dept","").strip(),
        "manage_dept":form.get("manage_dept","").strip(),
        "officer":form.get("officer","").strip(),
        "content":form.get("content","").strip(),
        "bid_time":form.get("bid_time","").strip(),
        "status":form.get("status","立项"),
    }

FORM_BODY = """
<div class="card"><h2>{{title}}</h2>
{% if number %}<p><b>编号：{{number}}</b>　流程线 {{line}}　代理：{{ag(agency_code) or '无'}}　
  <span style="color:#888">（编号与代理不可改）</span></p>{% endif %}
<form method="post">
  <label>项目名称 *</label>
  <input name="name" style="width:100%" required value="{{f.name}}" placeholder="如：2026年XX耗材采购项目">
  <div class="row">
    <div><label>预算金额（元）</label>
      <input name="amount" id="amount" type="number" step="0.01" style="width:100%" value="{{f.amount_raw}}" placeholder="填具体金额" oninput="autoMethod()">
      <label style="display:inline-flex;align-items:center;gap:6px;margin-top:6px;font-size:13px">
        <input type="checkbox" name="is_unit_price" id="unit" {{'checked' if f.is_unit_price}} onchange="onUnit()"> 挂网耗材/招单价（无固定预算，按≥5万竞选）
      </label>
    </div>
    <div><label>采购方式（按金额自动，仅可改单一来源）</label>
      <select name="method" id="method" style="width:100%" onchange="onMethod()">
        {% for m in METHODS %}<option value="{{m}}" {{'selected' if f.method==m}}>{{m}}</option>{% endfor %}
      </select>
      <div class="hint" id="mhint"></div>
    </div>
  </div>
  <div class="row" id="soleRow" style="display:none">
    <div><label>单一来源：是否走代理机构？</label>
      <select name="sole_use_agency" id="sole" style="width:100%" onchange="onSole()">
        <option value="no" {{'selected' if f.sole_use_agency=='no'}}>不走代理（NJYYXJ）</option>
        <option value="yes" {{'selected' if f.sole_use_agency=='yes'}}>走代理（NJYYJX）</option>
      </select>
    </div>
  </div>
  <div class="row">
    <div id="agencyBox"><label>代理机构（走代理时必选）</label>
      <select name="agency_code" id="agency" style="width:100%">
        <option value="">（不走代理免选）</option>
        {% for a in agencies %}<option value="{{a['code']}}" {{'selected' if f.agency_code==a['code']}}>{{a['name']}}</option>{% endfor %}
      </select>
    </div>
    <div><label>项目经办人</label><input name="officer" style="width:100%" value="{{f.officer}}"></div>
  </div>
  <div class="row">
    <div><label>需求科室</label><input name="demand_dept" style="width:100%" value="{{f.demand_dept}}"></div>
    <div><label>归口管理科室</label><input name="manage_dept" style="width:100%" value="{{f.manage_dept}}"></div>
  </div>
  {% if show_status %}<div class="row">
    <div><label>当前状态</label><select name="status" style="width:100%">
      {% for s in STATUSES %}<option value="{{s}}" {{'selected' if f.status==s}}>{{s}}</option>{% endfor %}</select></div>
    <div><label>开标时间</label><input name="bid_time" style="width:100%" value="{{f.bid_time}}" placeholder="如 2026年5月27日16:00"></div>
  </div>{% endif %}
  <label>包号及采购内容</label>
  <textarea name="content" rows="3" style="width:100%">{{f.content}}</textarea>
  <div style="margin-top:16px">
    <button class="btn" name="action" value="submit">{{submit_text}}</button>
    {% if allow_draft %}<button class="btn gray" name="action" value="draft">存草稿</button>{% endif %}
    <a class="btn gray" href="{{url_for('project_flow_url')}}">取消</a>
  </div>
</form></div>
<script>
var HINT={{method_hint_json|safe}};var SOLE="{{M_SOLE}}";var LOCKED={{'true' if number else 'false'}};
function autoMethod(){
  if(LOCKED)return; // 编辑已立项的不自动改
  var u=document.getElementById('unit').checked;var ms=document.getElementById('method');
  if(u){setM(SOLE_TO_JX());return;}
  var v=parseFloat(document.getElementById('amount').value||'0');
  var cur=ms.value;
  if(cur==SOLE)return; // 用户已选单一来源，不覆盖
  if(v<20000)setM("{{M_YIJIA}}");else if(v<50000)setM("{{M_XUNJIA}}");else setM("{{M_JINGXUAN}}");
}
function SOLE_TO_JX(){return "{{M_JINGXUAN}}";}
function setM(m){document.getElementById('method').value=m;onMethod();}
function onMethod(){var m=document.getElementById('method').value;
  document.getElementById('mhint').textContent=HINT[m]||'';
  document.getElementById('soleRow').style.display=(m==SOLE)?'flex':'none';
  syncAgency();}
function onSole(){syncAgency();}
function onUnit(){var u=document.getElementById('unit').checked;
  document.getElementById('amount').disabled=u;if(u){document.getElementById('amount').value='';}
  autoMethod();}
function syncAgency(){ /* 仅提示，不强制 */ }
autoMethod();onMethod();onUnit();
</script>
"""

@app.route("/project/new", methods=["GET","POST"])
@login_required
def new_project():
    db=get_db()
    agencies=db.execute("SELECT code,name FROM agencies WHERE active=1").fetchall()
    f={"name":"","amount_raw":"","is_unit_price":False,"method":N.M_YIJIA,"sole_use_agency":"",
       "agency_code":"","demand_dept":"","manage_dept":"","officer":session.get("display_name",""),
       "content":"","bid_time":"","status":"立项"}
    if request.method=="POST":
        f=_read_form(request.form)
        action=request.form.get("action","submit")
        try:
            if not f["name"]: raise ValueError("项目名称不能为空")
            now=datetime.datetime.now().isoformat(timespec="seconds")
            if action=="draft":
                # 草稿：不生成编号、不占序号
                db.execute("""INSERT INTO projects
                  (number,name,amount,line,method,demand_dept,manage_dept,agency_code,officer,content,
                   status,is_draft,created_by,created_at,updated_at)
                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                  ("", f["name"], (float(f["amount_raw"]) if f["amount_raw"] else 0), "",
                   f["method"], f["demand_dept"], f["manage_dept"], f["agency_code"],
                   f["officer"], f["content"], "草稿", 1, session["user"], now, now))
                db.commit(); flash("已存为草稿（未生成编号）"); return redirect(url_for("project_flow_url"))
            # 正式立项
            if not f["method"]: raise ValueError("请选择采购方式")
            amount=None if f["is_unit_price"] else (float(f["amount_raw"]) if f["amount_raw"] else None)
            if not f["is_unit_price"] and amount is None: raise ValueError("请填写金额或勾选招单价")
            sole=(f["sole_use_agency"]=="yes") if f["method"]==N.M_SOLE else None
            use_agency,line=N.decide(f["method"],amount,f["is_unit_price"],sole)
            if use_agency and not f["agency_code"]: raise ValueError("走代理机构的项目必须选择代理机构")
            number=N.gen_number(db, use_agency, f["agency_code"] if use_agency else None)
            db.execute("""INSERT INTO projects
              (number,name,amount,line,method,demand_dept,manage_dept,agency_code,officer,content,
               status,is_draft,created_by,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (number,f["name"], (amount if amount else 0), line, f["method"],
               f["demand_dept"], f["manage_dept"], f["agency_code"] if use_agency else "",
               f["officer"], f["content"], "立项", 0, session["user"], now, now))
            db.commit(); flash(f"立项成功，编号 {number}（{'走代理' if use_agency else '不走代理'}，线{line}）")
            return redirect(url_for("project_flow_url"))
        except Exception as e:
            flash(f"操作失败：{e}（已保留填写内容）")
    return render(FORM_BODY, active="pm_new", page_title="项目立项", title="项目立项",
                  f=f, agencies=agencies, METHODS=METHODS, STATUSES=STATUSES,
                  show_status=False, allow_draft=True, number="", line="", agency_code="",
                  submit_text="正式立项（生成编号）", M_SOLE=N.M_SOLE, M_YIJIA=N.M_YIJIA,
                  M_XUNJIA=N.M_XUNJIA, M_JINGXUAN=N.M_JINGXUAN, ag=agency_name,
                  method_hint_json=_json.dumps(METHOD_HINT, ensure_ascii=False))

@app.route("/project/<int:pid>", methods=["GET","POST"])
@login_required
def edit_project(pid):
    db=get_db()
    agencies=db.execute("SELECT code,name FROM agencies WHERE active=1").fetchall()
    p=db.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    if not p: flash("项目不存在"); return redirect(url_for("project_flow_url"))
    is_draft=bool(p["is_draft"]) if "is_draft" in p.keys() else False
    if request.method=="POST":
        f=_read_form(request.form)
        action=request.form.get("action","submit")
        try:
            if not f["name"]: raise ValueError("项目名称不能为空")
            now=datetime.datetime.now().isoformat(timespec="seconds")
            if is_draft and action=="submit":
                # 草稿转正式：此时才生成编号
                amount=None if f["is_unit_price"] else (float(f["amount_raw"]) if f["amount_raw"] else None)
                if not f["is_unit_price"] and amount is None: raise ValueError("请填写金额或勾选招单价")
                sole=(f["sole_use_agency"]=="yes") if f["method"]==N.M_SOLE else None
                use_agency,line=N.decide(f["method"],amount,f["is_unit_price"],sole)
                if use_agency and not f["agency_code"]: raise ValueError("走代理必须选代理机构")
                number=N.gen_number(db, use_agency, f["agency_code"] if use_agency else None)
                db.execute("""UPDATE projects SET number=?,name=?,amount=?,line=?,method=?,
                    demand_dept=?,manage_dept=?,agency_code=?,officer=?,content=?,status=?,
                    is_draft=0,bid_time=?,updated_at=? WHERE id=?""",
                  (number,f["name"], (amount if amount else 0),line,f["method"],f["demand_dept"],
                   f["manage_dept"], f["agency_code"] if use_agency else "", f["officer"],
                   f["content"],"立项",f["bid_time"],now,pid))
                db.commit(); flash(f"草稿已立项，编号 {number}"); return redirect(url_for("project_flow_url"))
            # 普通保存（已立项的不改编号；草稿存草稿）
            db.execute("""UPDATE projects SET name=?,method=?,demand_dept=?,manage_dept=?,
                officer=?,content=?,status=?,bid_time=?,updated_at=? WHERE id=?""",
              (f["name"], f["method"] or p["method"], f["demand_dept"], f["manage_dept"],
               f["officer"], f["content"], f["status"] if not is_draft else "草稿",
               f["bid_time"], now, pid))
            db.commit(); flash("已保存"); return redirect(url_for("project_flow_url"))
        except Exception as e:
            flash(f"保存失败：{e}（已保留填写内容）")
    f={"name":p["name"],"amount_raw":("" if (p["amount"] in (0,None)) else str(int(p["amount"]))),
       "is_unit_price":(p["amount"] in (0,None)) and not is_draft,
       "method":p["method"] or N.M_YIJIA,"sole_use_agency":"","agency_code":p["agency_code"],
       "demand_dept":p["demand_dept"],"manage_dept":p["manage_dept"],"officer":p["officer"],
       "content":p["content"],"bid_time":p["bid_time"],"status":p["status"]}
    return render(FORM_BODY, active="pm_flow",
                  page_title=("编辑草稿" if is_draft else "编辑项目"),
                  title=("编辑草稿（可正式立项）" if is_draft else "编辑项目"),
                  f=f, agencies=agencies, METHODS=METHODS, STATUSES=STATUSES,
                  show_status=(not is_draft),
                  allow_draft=is_draft,
                  number=("" if is_draft else p["number"]),
                  line=p["line"], agency_code=p["agency_code"],
                  submit_text=("正式立项（生成编号）" if is_draft else "保存修改"),
                  M_SOLE=N.M_SOLE, M_YIJIA=N.M_YIJIA, M_XUNJIA=N.M_XUNJIA, M_JINGXUAN=N.M_JINGXUAN,
                  ag=agency_name, method_hint_json=_json.dumps(METHOD_HINT, ensure_ascii=False))

@app.route("/project/<int:pid>/delete")
@login_required
def del_project(pid):
    get_db().execute("DELETE FROM projects WHERE id=?", (pid,)); get_db().commit()
    flash("已删除"); return redirect(url_for("project_flow_url"))

# 给模板用的列表页 url
@app.route("/flow")
@login_required
def project_flow_url():
    return project_flow()


# ---------- 开标管理（轻整合：展示有开标时间的项目 + 能否开标标记）----------
def bid_manage():
    db = get_db()
    if session.get("role")=="agency":
        rows = db.execute("""SELECT * FROM projects WHERE agency_code=? AND COALESCE(is_draft,0)=0
                             ORDER BY (bid_time='') ASC, bid_time ASC""",
                          (session.get("agency_code",""),)).fetchall()
    else:
        rows = db.execute("""SELECT * FROM projects WHERE COALESCE(is_draft,0)=0
                             ORDER BY (bid_time='') ASC, bid_time ASC""").fetchall()
    can_mark = session.get("role") in ("agency","officer")
    body = """<div class="card"><h2>开标管理</h2>
    <p class="hint">展示已立项项目的开标安排。代理机构 / 经办人可标记"能否开标"。</p>
    <table><tr><th>编号</th><th>项目名称</th><th>采购方式</th><th>代理机构</th>
      <th>开标时间</th><th>能否开标</th><th>状态</th>{% if can_mark %}<th>操作</th>{% endif %}</tr>
    {% for p in rows %}<tr>
      <td><a class="proj" href="{{url_for('edit_project',pid=p['id'])}}">{{p['number']}}</a></td>
      <td>{{p['name']}}</td><td>{{p['method']}}</td><td>{{ag(p['agency_code'])}}</td>
      <td>{{p['bid_time'] or '—'}}</td>
      <td>{% if p['can_open']=='可开标' %}<span class="tag" style="background:#27ae60;color:#fff">可开标</span>
          {% elif p['can_open']=='流标' %}<span class="tag" style="background:#c0392b;color:#fff">流标</span>
          {% else %}<span class="tag">未判定</span>{% endif %}</td>
      <td>{{p['status']}}</td>
      {% if can_mark %}<td>
        <a class="btn sm" href="{{url_for('mark_bid',pid=p['id'],v='可开标')}}">可开标</a>
        <a class="btn sm red" href="{{url_for('mark_bid',pid=p['id'],v='流标')}}">流标</a>
      </td>{% endif %}
    </tr>{% else %}<tr><td colspan="8" style="text-align:center;color:#999;padding:24px">暂无项目</td></tr>{% endfor %}
    </table></div>"""
    return render(body, active="pm_bid", page_title="开标管理", rows=rows, can_mark=can_mark, ag=agency_name)

@app.route("/bid/<int:pid>/mark/<v>")
@login_required
def mark_bid(pid, v):
    if session.get("role") not in ("agency","officer"):
        flash("无权限标记"); return redirect(url_for("page", mod="pm_bid"))
    if v not in ("可开标","流标"):
        flash("参数错误"); return redirect(url_for("page", mod="pm_bid"))
    # 代理机构只能标记自己的项目
    db = get_db()
    p = db.execute("SELECT agency_code FROM projects WHERE id=?", (pid,)).fetchone()
    if session.get("role")=="agency" and (not p or p["agency_code"]!=session.get("agency_code")):
        flash("只能标记自己的项目"); return redirect(url_for("page", mod="pm_bid"))
    db.execute("UPDATE projects SET can_open=? WHERE id=?", (v, pid)); db.commit()
    flash(f"已标记为「{v}」")
    return redirect(url_for("page", mod="pm_bid"))

# ---------- 修改密码 ----------
@app.route("/chpwd", methods=["GET","POST"])
@login_required
def chpwd():
    db = get_db()
    if request.method=="POST":
        old=request.form.get("old",""); n1=request.form.get("n1",""); n2=request.form.get("n2","")
        row=db.execute("SELECT * FROM users WHERE username=?", (session["user"],)).fetchone()
        if not row or hash_pw(old,row["salt"])!=row["pw_hash"]:
            flash("原密码错误")
        elif not n1 or n1!=n2:
            flash("两次新密码不一致或为空")
        else:
            import secrets as _s
            salt=_s.token_hex(16)
            db.execute("UPDATE users SET salt=?, pw_hash=? WHERE username=?",
                       (salt, hash_pw(n1,salt), session["user"])); db.commit()
            flash("密码已修改")
            return redirect(url_for("page", mod="pm_flow"))
    body="""<div class="card" style="max-width:420px"><h2>修改密码</h2>
    <form method="post"><label>原密码</label><input type="password" name="old" style="width:100%">
    <label>新密码</label><input type="password" name="n1" style="width:100%">
    <label>确认新密码</label><input type="password" name="n2" style="width:100%">
    <div style="margin-top:14px"><button class="btn">修改</button></div></form></div>"""
    return render(body, active="", page_title="修改密码")


if __name__=="__main__":
    if not os.path.exists(DB):
        print("[!] 先运行 python db_init.py")
    else:
        print(f"[*] 启动: http://0.0.0.0:{PORT}")
        app.run(host="0.0.0.0", port=PORT, debug=False)
