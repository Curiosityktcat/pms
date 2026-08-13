---
title: 经办人 AI 助理
order: 40
summary: 基于开源 pi 的 agent，一人一个 docker 盒子，能查 PMS、记事、出汇报，写操作一律提议→确认
---

# 经办人 AI 助理（officer-agent）

一句话：**一个聪明、会记事、会成长的实习生**——你说人话它就干活，记住你说过的，越用越省心。

## 1. 为什么是 pi

旧的「牛马 agent」(`pms-agent` 3070) 大脑是手搓的 156 行 ReAct 循环，DeepSeek 无结构化输出 → 不调工具就口胡、教过的规则转头就忘。

方案是**换大脑保工具**：用开源 **pi**（`github.com/earendil-works/pi`，MIT，TS/Node）的成熟内核替换那个破循环，PMS 领域工具保留、以 HTTP 桥接。

- npm 包：`@earendil-works/pi-coding-agent` + `pi-ai`，均 **0.81.1**
- 用法是 **embed SDK**（不是跑 pi CLI）：`createAgentSession({model, cwd, tools, resourceLoader, sessionManager})`，pi 当大脑，我们控一切

## 2. 一人一个盒子

| 容器 | 端口 | 归属 | PMS 服务账号 | 数据卷 |
|---|---|---|---|---|
| `officer-agent` | 127.0.0.1:3071 | 黄新博 | `agent-hxb` | `officer-agent-data` |
| `officer-zyj` | 127.0.0.1:3072 | 郑跃俊 | `agent-zyj` | `officer-zyj-data` |

**同一个镜像 `officer-agent:auth`，靠环境变量区分**：`AGENT_PROFILE`（用途）、`AGENT_OWNER`（归属人）、`PMS_AGENT_USER`（PMS 服务账号）、独立 data 卷。物理隔离，记忆不串味。

部署脚本：

```bash
bash /tmp/deploy_box.sh <容器名> <端口> <OWNER> <密码文件> [profile] [PMS账号]
# 例：bash /tmp/deploy_box.sh officer-zyj 3072 郑跃俊 /home/huangxb/pms/.agent_zyj_pw pms agent-zyj
```

**加一个新经办人的完整步骤**：

1. 建 PMS 服务账号（pbkdf2_hmac sha256 200000 轮，同 `~/pms/backend/services/auth.py`），`role=officer`、`display_name=本人姓名`，随机密码写 600 权限文件
2. 把账号加进 PMS 免滑块白名单：`~/pms/backend/routes/auth_api.py` 的 `PMS_AGENT_USERS`（默认 `agent-hxb,agent-zyj`）
3. `deploy_box.sh` 起容器
4. PMS 反代加一行映射：`~/pms/backend/app.py` 的 `_OFFICER_BOXES`
5. 重启 `pms.service`

## 3. 工具清单（18 个）

代码在 `~/platform/services/officer-agent/src/`：

| 文件 | 工具 |
|---|---|
| `memory.ts` | `remember` / `recall` |
| `pms.ts` | `find_project`、`project_progress`、**`project_dossier`**（项目全档一次拉全）、`list_pool`、`my_todos`、`list_contracts`、**`supervise`**（全局卡点扫描）、`pending_confirmations`、`search_regulations`、`list_project_files`、`read_document`，以及 4 个写操作提议 |
| `report.ts` | `make_report`（HTML 汇报） |

**当前没有给任何文件工具和 bash**——`TOOLS` 白名单里 18 个全是自定义工具，pi 内建的 `read/bash/edit/write/grep/find/ls` 一个都没启用（`createAgentSession` 传了 `tools` 数组就只启用列表里的）。

## 4. 写操作的安全闭环（重要）

**agent 永远只提议，不自动写。**

```ts
// pms.ts
const pendingActions = new Map<string, PendingAction>();
// propose_* 工具只做 addPending({... run: () => postData(...) })
// 真正的 postData 只在 confirmPending() 里发生
```

四个提议工具：`propose_confirm_announcement`、`propose_confirm_result`、`propose_lixiang`（立项）、`propose_contract_push`（推送到政府 rd-web 平台）。

HTTP 层：`GET /api/pending`、`POST /api/action/confirm`、`POST /api/action/cancel`。前端在牛马面板底部渲染成黄色「待确认写操作」卡片。

> **`/api/action/confirm` 现在需要 `action` 权限位**，见《鉴权与安全》。

## 5. 记忆系统

- 存储：`/data/memory.json`（受限工具写入，不是裸 `write`）
- 纪律（写死在工具描述里）：**只记 PMS 表不知道的东西**——偏好、工作风格、学到的规则、一次性交代；**绝不复制项目数据**（名称/金额/阶段/进度）。项目事实的真源永远是那张表，存一份必过期打架。
- 分类：偏好 / 工作风格 / 规则 / 其他
- 上下文四层：① 工作记忆 = pi session；② 长期记忆 = `remember`/`recall`；③ 项目快照 = 每次从表实时取；④ 文件 = cwd + 文件工具（未开）

## 6. 硬规则 vs 软规则（踩过的坑）

**教训**：命名格式是硬规则，却被当软规则塞进记忆里 → 模型记住了也不照做，"建议性约束"靠提示词永远治不好。

**分界**：

- **硬规则**（能写成模板/正则）→ **进代码强制**。例：立项命名由 `buildProjectName()` 代码拼装
- **软规则**（判断性个人偏好）→ 进记忆

### 立项命名的权威规则

格式 = **年度 + 标的事项 + "采购项目"**，例：`2026年动脉血气针配送服务采购项目`。

- 年度前缀、"采购项目"后缀 = 代码自动填
- 中间标的事项 = 模型拟（物 + 性质、简洁）
- **硬闸门：名字里绝不能出现需求科室**——拿项目的 `demand_dept` 字段比对，含科室名就自动剥掉
- **为什么**：名字带需求科室 → 供应商照名字直接找临床科室领导公关、绕过集采渠道。这是廉政红线。
- **范围钉死在命名这一条**：不要引申成"处处隐藏需求科室"。过度隐藏关键信息 → 供应商无法准确核算成本 → 招投诉。采购是在监管、供应商、单位意向、社会影响之间取平衡，不是把某个约束拉满。

> **通用教训**：agent 最危险的不是记不住，而是**把一条窄规则过度外推成一刀切政策**。硬规则窄且精确按字面执行；"平衡/披露取舍"是随项目变的人的软判断，绝不交给 agent 系统化。

## 7. 模型与网关

- `models.json` 注册 provider `local-gateway` → `http://host.docker.internal:8600/v1`，`api: openai-completions`，`compat: qwen-chat-template`
- 当前 `MODEL_ID=deepseek-v4-flash`；换模型只改 env 重建容器即可（不用改代码）
- 本地 Qwen 可用（数据完全不出内网），但慢；上下文受 `llama-server -np` 分槽限制（现 `-np 2` = 每槽 4096 token）

**网关为 pi 打过两个补丁**（都在 `~/platform/services/llm-gateway/app.py`）：

1. **`tools` 透传**——原来网关只读 messages/temperature/max_tokens，会把 `tools` 吞掉
2. **流式 SSE 分支**——pi 的 `openai-completions` 强制流式，原网关是非流式 JSON，会报 "Stream ended without finish_reason"

> ⚠️ 这两个补丁当时是**热替换**（`docker cp` + restart），宿主源码已同步但**镜像未重建**。`docker compose up -d`（不带 `--build`）或容器被 recreate 会丢补丁 → 需择机 `docker compose up -d --build llm-gateway` 烧进镜像。

## 8. 前端入口

- PMS 右侧常驻面板 `NiumaAssistant.tsx`（🐮 牛马），只对有盒子的账号显示
- 走 PMS 同源反代 `/officer-agent/*`，SSE 流式
- 汇报渲染成可点文件卡片 → Modal iframe 内预览（不跳页）

## 9. 排障

```bash
docker logs officer-agent --tail 50
curl -s 127.0.0.1:3071/healthz              # 放行，不需要凭据
docker exec officer-agent cat /data/memory.json
docker exec officer-agent tail -5 /data/audit.log
```

| 症状 | 多半是 |
|---|---|
| PMS 登录 401 | `PMS_AGENT_USER` 没设或与密码文件不匹配；或该账号不在免滑块白名单 |
| 改了代码没生效 | **`docker restart` 不换镜像层**，要 `docker rm -f` + `docker run`（或用 `deploy_box.sh`） |
| 报 "Stream ended without finish_reason" | llm-gateway 的流式补丁掉了（容器被 recreate 过） |
| 上下文超限 | 本地 Qwen 每槽 4096；工具多+全档时吃紧，可把 `llama-server -np` 降到 1 |
