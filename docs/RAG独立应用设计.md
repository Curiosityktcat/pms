# 独立 RAG 应用（rag.curiosityktcat.cn）脚手架设计

> 目标：把"RAG 管理 + 评审工作流在线调整 + 数据/知识库管理"做成一个独立应用，
> 跑在本机 `:5001`，对外经 Cloudflare 隧道 `rag.curiosityktcat.cn`、对内经局域网
> `http://172.1.14.12:5001` 访问。与 PMS（:1573）进程独立、可分别部署重启。

---

## 0. 关键事实（已就绪，降低落地成本）

- **隧道路由已配好**：`/home/huangxb/.cloudflared/config.yml` 里 `rag.curiosityktcat.cn → localhost:5001`。所以新应用只要监听 5001，公网域名即刻可用，无需改 DNS/隧道。
- **局域网直连**：监听 `0.0.0.0:5001` 即可 `http://172.1.14.12:5001` 访问。
- **PMS 技术栈可复用**：前端 React + Vite + TS + Antd，后端 Flask + SQLAlchemy + SQLite。新应用沿用同栈，减少学习与维护成本。
- **嵌入/混合检索/两轮闭环已落在 PMS 后端**（`services/bid_review.py`、`services/llm_client.py`）。新应用不重复造，而是**复用这套服务层**。

---

## 1. 定位：它和 PMS 的分工

| | PMS（:1573，pms.curiosityktcat.cn） | RAG 应用（:5001，rag.curiosityktcat.cn） |
|---|---|---|
| 面向 | 业务人员日常采购/评审操作 | 管理员/运维：调参、管知识、看效果、管数据 |
| 职责 | 跑评审流程、出结果 | **配置和优化**评审流程，管理 RAG 资产 |
| 关系 | 执行 | 控制台 / 后台 |

一句话：**PMS 是"用"，RAG 应用是"管和调"。**

---

## 2. 三大功能模块（对应你的需求）

### A. RAG 管理
- 嵌入模型管理（端点/模型/维度，连通性测试）——把 PMS 里那张配置卡片升级成完整控制台；
- 检索参数在线调：`BR_MAX_ROUNDS`（闭环轮数）、`EXTRACT_MAX_CHARS`（选页预算）、`PAGES_PER_BATCH`、关键词词表、语义 query 模板；
- 检索效果可视化：对某采购文件，展示"关键词命中页 / 语义召回页 / 最终入选页"，便于调参；
- 知识库管理：耗子 AI 知识库文件的增删改、（未来）向量化状态。

### B. 评审工作流在线调整
- 把投标审查的步骤（概要 / 资格 / 实质性 / 商务 / 评分 / 报价）做成**可视化流水线**；
- **每步一键切换模型**：DeepSeek（在线·快）或 Qwen3.6（本机·免费），逐步独立配置；
- 每步的 system/user 提示词**在线编辑 + 版本留存**，改完即生效，无需改代码发版；
- 试运行：选一份样本文件，单步/整链跑一遍看输出，调好再上线。

### C. 数据库管理
- 浏览/检索 PMS 的关键表（审查任务、条目、结果明细、LLM 用量、配置）；
- 受控编辑（带审计日志），危险操作二次确认；
- 导出/备份触发。

> ⚠️ 安全：数据库管理与提示词在线编辑权限大，**必须强鉴权 + 操作审计**（见 §4）。

---

## 3. 目录结构（脚手架）

```
/home/huangxb/rag-admin/            # 与 pms 同级，独立仓库/目录
├── backend/
│   ├── app.py                      # Flask 入口，监听 0.0.0.0:5001
│   ├── config.py                   # DB 路径、PMS 服务地址、密钥
│   ├── routes/
│   │   ├── auth_api.py             # 登录/鉴权（见 §4 方案）
│   │   ├── rag_config_api.py       # A：嵌入/检索参数
│   │   ├── workflow_api.py         # B：工作流步骤、每步模型、提示词
│   │   ├── playground_api.py       # B：试运行/单步调试
│   │   └── dbadmin_api.py          # C：数据库管理（带审计）
│   ├── models/                     # 新增表：workflow_step / prompt_version / audit_log
│   └── services/
│       └── pms_bridge.py           # 复用 PMS 的 services（见 §5）
├── frontend/                       # React + Vite + TS + Antd（复刻 PMS 前端骨架）
│   └── src/pages/  RagConfig / Workflow / Playground / DbAdmin / Login
├── rag-admin.service               # systemd 单元（仿 pms.service）
└── rebuild.sh                      # 仿 PMS 的构建+重启
```

---

## 4. 数据与鉴权边界（**需你拍板**）

**数据库**——两种方案：
- **方案①（推荐·MVP）共用 PMS 的 `pms.db`**：RAG 应用直连同一个 SQLite，读评审数据、写自己的新表（workflow/prompt/audit）。落地最快，数据天然一致。代价：两进程写同一 SQLite 要注意并发（SQLite 支持，但写锁；RAG 应用以读+低频写为主，问题不大）。
- **方案②独立库 + API 调用 PMS**：RAG 应用有自己的库，通过 PMS 暴露的 API 取数据。彻底解耦，但要给 PMS 加一批内部 API，工程量大。

**鉴权**——两种方案：
- **方案①（推荐）复用 PMS 账号体系**：共用 `pms.db` 的用户表 + 同样的 session 机制；仅允许管理员角色访问。
- **方案②独立账号**：RAG 应用自己一套登录。更隔离，但多一套维护。

> 我的建议：**MVP 走"共用 pms.db + 复用 PMS 账号、仅管理员可进"**，最快让 `rag.curiosityktcat.cn` 通起来；后续若要彻底解耦再演进到方案②。

---

## 5. 复用 PMS 服务层（不重复造轮子）

RAG 应用的"试运行/调参"要真正跑检索，可两种接法：
- **进程内复用**：把 `pms/backend` 加入 PYTHONPATH，`pms_bridge.py` 直接 import `services.bid_review` / `services.llm_client`。最省事，但耦合 PMS 代码路径。
- **HTTP 复用**：PMS 暴露"按配置跑一次抽取/检索"的内部接口，RAG 应用调用。更解耦。

MVP 建议进程内复用（共目录），后续抽成共享库。

---

## 6. 部署

1. 后端：`rag-admin.service`（仿 `pms.service`），`ExecStart` 跑 `app.py` 监听 5001，`Restart=on-failure`；
2. 前端：`rebuild.sh` 构建 dist，Flask 托管；
3. 公网：**无需改 cloudflared**（`rag→5001` 已配），`sudo systemctl start rag-admin` 后 `rag.curiosityktcat.cn` 即通；
4. 局域网：`http://172.1.14.12:5001`。

---

## 7. 分期实施路线

- **M1（脚手架打通）**：Flask :5001 + 前端骨架 + 复用 PMS 登录 + 一个"嵌入/检索参数"配置页。目标：`rag.curiosityktcat.cn` 能登录、能改嵌入配置。
- **M2（工作流在线调整）**：步骤可视化 + 每步一键切 DeepSeek/Qwen3.6 + 提示词在线编辑与版本；改完 PMS 评审即按新配置跑（需 PMS 评审改为读取这些配置）。
- **M3（试运行调试台）**：样本文件单步/整链试跑，可视化命中页与输出。
- **M4（数据库管理）**：表浏览/受控编辑 + 审计日志 + 备份导出。

---

## 8. 待你拍板的决策点

1. **数据库**：共用 `pms.db`（推荐，快）还是独立库？
2. **鉴权**：复用 PMS 账号（推荐）还是独立账号？
3. **服务复用**：进程内 import PMS（推荐，快）还是 HTTP 接口解耦？
4. **目录**：放在 `/home/huangxb/rag-admin/`（独立）还是 `pms/` 仓库内子目录？
5. **M2 的前置**：工作流"在线调参"要真正生效，需要把 PMS 评审里现在写死的提示词/模型/参数改为"从配置表读取"——这是一笔 PMS 侧的改造，确认要做后我再排。

> 建议先按 §4 推荐项做 **M1 脚手架**，把域名跑通、把"嵌入/检索参数在线配置"这个最高频诉求落地，再逐步推进 M2–M4。
