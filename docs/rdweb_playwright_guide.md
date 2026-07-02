# rd-web Playwright 自动填报开发指南

适用场景：PMS 系统需要自动打开 rd-web 页面、填写表单并提交的所有业务模块（合同审签单、采购项目审批、代理协议审签等）。

---

## 一、整体架构

```
PMS 前端
  └─ POST /api/contracts/{id}/submit-to-rdweb
        └─ Flask 路由（contract_api.py）
              └─ threading.Thread(daemon=True) 后台启动
                    └─ services/contract_submit.py submit_contract()
                          └─ Playwright sync_api 打开 Chrome 无头浏览器
                                └─ rd-web iframe 内填表 → 提交
```

**前端轮询**：提交后前端每 2.5 秒轮询 `/api/contracts/{id}/rdweb-status`，直到 `running=false` 才停止。全程约 2–3 分钟。

---

## 二、rd-web 页面特点（必须了解）

### 1. 整个业务区是 iframe

rd-web 的内容在一个 `<iframe>` 里（URL 含 `APP_MARK = "6642c01d66eb836a97bbccb2"`）。

- `pg`：主页面（Playwright Page 对象），坐标为主页面绝对坐标
- `fr`：iframe Frame 对象，通过 `pg.frames` 里匹配 APP_MARK 获取
- **关键**：`fr.evaluate()` 返回的 `getBoundingClientRect()` 坐标是 **frame 内坐标**，当 iframe 撑满整个视口时 frame 坐标 = 主页面坐标

### 2. 表单是 AngularJS ng-model

rd-web 使用 AngularJS，双向数据绑定靠 `$watch`。

- **必须用 Playwright 的 `fill()` 方法**，它会触发真实的 focus/input/change 事件
- **不能用 JS 直接赋值**（`element.value = ...` 不触发 `$watch`，ng-model 不会更新）
- 正确用法：`fr.locator(":focus").fill(value)` 或 `locator.fill(value)`

### 3. 表单内有两套 `input[placeholder="请输入"]`

打开新建表单后，页面同时存在：

| 区域 | x 坐标 | y 坐标 | 数量 | 用途 |
|------|---------|---------|------|------|
| 搜索栏 | x < 700 | y ≈ 55 | 3 个 | 列表过滤搜索 |
| 表单区 | x ≈ 750 | y = 76~1084 | 13 个 | 真正的表单字段 |

搜索栏的标签（合同名称、合同编码等）和表单区标签**完全同名**，按文字查找 input 时极易匹配到搜索栏。

**解决方案**：查找 input 时过滤 `ri.y > 60`，排除 y≈55 的搜索栏 input。

### 4. 表单最后几行可能超出 viewport

viewport 设为 `1920×1080`，但表单高度超过 1080px。乙方地址等字段的 y 坐标可能到 1099，`pg.mouse.click(x, 1099)` 会打偏。

**解决方案**：用 JS `inp.scrollIntoView({block:'center', behavior:'instant'})` + `inp.focus()` 替代 `mouse.click`，再用 `fr.locator(":focus").fill(value)` 填值。

### 5. 每个可见 input 有 2 个隐藏的兄弟 input

AngularJS 的内部实现，`w=0, h=0` 的隐藏 input。过滤时要加 `r.width > 0 && r.height > 0`。

---

## 三、关键操作的实现方式

### 填写文本字段（`_fill_text_fields`）

```python
ok = fr.evaluate(f"""() => {{
    const target = {repr(label)};
    for (const e of document.querySelectorAll('*')) {{
        const txt = (e.innerText || '').trim().replace(/\*/g, '').trim();
        if (txt !== target) continue;
        const r = e.getBoundingClientRect();
        if (r.width === 0 || r.height === 0 || r.height > 50) continue;
        let p = e.parentElement;
        for (let i = 0; i < 6 && p; i++, p = p.parentElement) {{
            const inp = p.querySelector('input[placeholder="请输入"]');
            if (inp) {{
                const ri = inp.getBoundingClientRect();
                // ri.y > 60 排除顶部搜索栏（y≈55）
                if (ri.width > 0 && ri.height > 0 && ri.y > 60) {{
                    inp.scrollIntoView({{block: 'center', behavior: 'instant'}});
                    inp.focus();
                    return true;
                }}
            }}
        }}
    }}
    return false;
}}""")
if ok:
    fr.locator(":focus").fill(str(value), timeout=3000)
```

### 选择经办人（`_fill_officer`）

人员选择框是弹出的树形对话框，部门默认折叠。

```
流程：
1. 点击经办人 input（触发弹框）
2. 等待 input[placeholder="输入查找的姓名"] 出现
3. 点击 fa-caret-right / iconCaret 展开部门（循环最多 8 次）
4. 每次展开后查找目标姓名行，点击同行的 button.selectPersonBtn
5. 点「确定」按钮
```

关键代码段：
```python
# 找人名并点击选择按钮（通过 selectPersonBtn 而非直接点名字）
pos = pg.evaluate(f"""() => {{
    const name = {repr(officer)};
    let nameY = -1;
    for (const e of document.querySelectorAll('*')) {{
        const t = (e.innerText || '').trim();
        if (t !== name) continue;
        const r = e.getBoundingClientRect();
        // y > 140 排除导航栏，x < 850 排除右侧已选面板
        if (r.width === 0 || r.height === 0 || r.y < 140 || r.x > 850) continue;
        nameY = r.y + r.height / 2;
        break;
    }}
    if (nameY < 0) return null;
    for (const btn of document.querySelectorAll('button.selectPersonBtn')) {{
        const r = btn.getBoundingClientRect();
        if (Math.abs(r.y + r.height / 2 - nameY) > 15) continue;
        if (r.width === 0 || r.height === 0) continue;
        return {{x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)}};
    }}
    return null;
}}""")
```

### 上传附件（`_upload_one`）

使用 Playwright 的 `FilePayload`（内存上传），保留原始文件名：

```python
with pg.expect_file_chooser(timeout=6000) as fc_info:
    upload_btn.click(timeout=3000)
fc_info.value.set_files([{
    "name": display_name,
    "mimeType": mime,
    "buffer": file_bytes
}])
```

等待上传完成：等文件名出现在 `.ui-dialog` 里，再点 `button.popConfirm` 确认。

---

## 四、后台线程架构（Flask）

```python
# contract_api.py
def _worker():
    from services.contract_submit import submit_contract as rdweb_submit
    try:
        res = rdweb_submit(data=rdweb_data, attachments=attachments_to_upload,
                           loginuser=_rdweb_user, password=_rdweb_pass)
        _rdweb[cid] = {"running": False, "ok": res["ok"], ...}
    except Exception as e:
        _rdweb[cid] = {"running": False, "ok": False, "msg": str(e)}

threading.Thread(target=_worker, daemon=True).start()
```

- `_rdweb` dict 按 cid 隔离，保存最新结果
- 防重复提交：线程启动前检查 `_rdweb[cid].get("running")`，True 则返回 429
- 账号映射：`get_rdweb_creds(display_name)` 从 `RdwebAccount` 表查对应 rd-web 手机号，找不到回退默认账号

---

## 五、前端轮询（HermesPanel.tsx）

```
提交 → POST directSubmitUrl → 开始 pollDirect(每 2.5s)
                                    ↓
                             GET directStatusUrl
                                    ↓
                             d.running === false → 停止，显示成功/失败
```

**关键修复**：组件挂载时立即检查一次状态，自动恢复进行中的任务（避免中途切换页面后看不到结果）：

```tsx
useEffect(() => {
  if (!directStatusUrl) return
  api.get(directStatusUrl).then(r => {
    const d = r.data.data
    if (d.running) {
      setDirectStatus(d)
      pollDirect(directStatusUrl)          // 自动恢复轮询
    } else if (d.ok !== null) {
      setDirectStatus(d)                   // 显示历史结果
    }
  }).catch(() => {})
}, [directStatusUrl])
```

---

## 六、常见问题排查

| 现象 | 原因 | 解决 |
|------|------|------|
| `人员选择框中未找到「XXX」` | 用户名只存在于导航栏（y<140）或右侧面板（x>850） | 检查 y>140 且 x<850 过滤；确认该用户在"我的"tab 的部门树里 |
| 合同名称/编码填到了搜索栏 | `_find_input_by_label` 命中 y≈55 的搜索框 | `ri.y > 60` 过滤已修复 |
| 乙方地址填不进去 | 字段在 y≈1099，超出 1080px 视口 | `scrollIntoView + focus` 已修复 |
| PMS 显示提交失败但实际成功 | rd-web 临时不可达，`pg.goto(timeout=45000)` 超时 | 属临时网络问题；再试即可；日志里看 `[rdweb]` 前缀行确认原因 |
| 提交后表单没关闭 | 某必填字段仍为空，AngularJS 校验失败 | 截图 `/tmp/submit_timeout.png` 看哪个字段标红 |
| Chrome 进程残留导致新提交慢 | 前次 Playwright 没正常关闭 | `pkill -f "chrome.*no-sandbox"` 清理 |

---

## 七、新业务接入清单

复用本模式开发新的 rd-web 自动填报时，逐项确认：

- [ ] 确认 iframe 的 APP_MARK（URL 特征字符串）
- [ ] 打开目标表单，用 `fr.evaluate` 扫描所有 `input` 的坐标和 placeholder，确认没有同名字段冲突
- [ ] 确认是否有超出 viewport 的字段（y > 1080），改用 `scrollIntoView + focus`
- [ ] 如有人员选择框，确认 `selectPersonBtn` 的 class 名和弹框的位置过滤条件
- [ ] 如有文件上传，确认按钮 class（`popshowfileuploadBtn`）和确认按钮（`popConfirm`）
- [ ] 在 `routes/utils.py` 的 `RdwebAccount` 表为新业务的经办人配置 rd-web 账号
- [ ] 在 Flask 路由里用 `threading.Thread(daemon=True)` 后台跑，加 `print("[rdweb]...")` 日志方便排查
- [ ] 前端用 `HermesPanel` 组件，传 `directSubmitUrl` 和 `directStatusUrl`

---

## 八、相关文件

| 文件 | 说明 |
|------|------|
| `backend/services/contract_submit.py` | 合同审签单 Playwright 实现（含所有填写策略） |
| `backend/routes/contract_api.py` | Flask 路由、后台线程、状态接口 |
| `frontend/src/components/HermesPanel.tsx` | 通用自动填报面板（轮询 + 状态展示） |
| `backend/services/procurement_approval_submit.py` | 采购项目审批（同样的 Playwright 模式） |
| `backend/services/agency_agreement_word.py` | 代理协议（Word 生成，非 Playwright） |
