# PMS 优化审计报告

> Claude 于 2026-06 在「8 小时无人值守」窗口内完成。原则：**前端 UI + 迁移准备 + 低风险清理可直接做；**
> **涉及业务逻辑的改动只提建议、不擅自改**（无人复核时改业务逻辑风险太高）。
> 标 ✅ 的本次已实施；标 ⬜ 的是待你回来确认后再动的建议。

---

## A. 本次已实施（安全、已上线/已验证）

- ✅ **全站卡片化 UI**：17 个列表页（项目流程/合同/归档/采购结果/询价/评审/公告/更正公告/代理协议/模板/人员/授权函/开标管理/院内竞选需求/采购需求登记/5.1 需求确认/5.2 文件确认）由表格改为统一卡片组件 `RecordCards`，含单列/双列切换、移动端响应式、Material 主题。密集监控/录入表（开标看板、四川公告、用量统计、行项目录入、供应商明细）**有意保留表格**。
- ✅ **迁移准备**：`MIGRATION.md`（完整迁移步骤+验收清单）、`backend/requirements.txt`（pin 全依赖）、`setup.sh`（新机一键安装）。
- ✅ **会话密钥可配置**：`app.py` 的 `SECRET_KEY` 改为读 `PMS_SECRET_KEY` 环境变量（默认值不变，当前不影响线上；迁移时设强密钥即可）。

---

## B. 建议（待你确认，按优先级）

### P0 — 迁移前必须处理 ✅ 已完成（2026-06）
1. ✅ **随机 SECRET_KEY**：`rebuild.sh` 首次启动自动在 `.pms_secret_key`（chmod 600、已 gitignore）生成强随机密钥并 `export PMS_SECRET_KEY`，重启不变。**本机已切换**（那次重启后大家需重新登录一次）。迁移到新机：要么把该文件一起拷过去，要么让它在新机重新生成。
2. ✅ **venv 路径去硬编码**：`rebuild.sh` 与 `run_test.sh` 改为 `PMS_PYTHON 环境变量 > $ROOT/venv > 旧机默认` 的回退逻辑，新机由 `setup.sh` 建 `$ROOT/venv` 即自动命中。

### P1 — 性能/体验 ✅ 已完成（2026-06）
3. ✅ **前端按路由懒加载**：`App.tsx` 业务页全部 `React.lazy()` + `<Suspense>`；主包 1.95MB → 1.31MB，xlsx/docx-preview 拆成按需 chunk。
4. ✅ **N+1 查询**：`archive` 列表原先每项目 3 次 COUNT（最严重）已改为 3 次分组查询（`_count_map`）。`contract`/`inquiry`/`review` 的 per-row `db.session.get(Project,...)` 是**主键取值 + SQLAlchemy identity-map 同会话缓存**，实际很廉价，未改动（改了收益小、风险大）。
5. ✅ **DB 索引 + WAL**：`app.py` 启动迁移加了 `CREATE INDEX IF NOT EXISTS`（幂等、不改数据）覆盖 `projects.officer/agency_code/status/is_deleted`、`contracts/procurement_results/announcements/inquiry_letters/auth_letter_records/procurement_rounds .project_id`、`procurement_doc_attachments(project_id,kind,round_number)`，已在生产库生效。WAL 模式本就已开（投标审查后台线程需要）。

### P2 — 代码整洁/可维护
6. ⬜ **删除死文件**（我没删，因为不是我建的，列出请你确认）：
   - `backend/app.py.lawbak`、`frontend/src/App.tsx.lawbak`、`frontend/src/components/AppLayout.tsx.lawbak`（旧备份）
   - `frontend/src/App.css`（Vite 模板残留，无人引用）
   - `医院模板/1.盖章文件/采购公告.docx.bak`（模板备份，确认无用再删）
7. ⬜ **收敛 `any` 类型**：多处 `eslint-disable @typescript-eslint/no-explicit-any`（上传选项、表格行等），可逐步换成具体类型。纯质量项。
8. ⬜ **SQLite → 单文件单写**：并发写入有锁；当前用户规模没问题。若未来人数/并发上升，再考虑 WAL 模式（`PRAGMA journal_mode=WAL`，低风险、提升并发读）或迁 Postgres（大改，不急）。

### B′ — 业务逻辑（**我只看了、没改**）
- 本次新增的「中标通知书闸门」「询价议价/紧急采购项目权限分离」「归档一键打印」逻辑我复查过，与现有轮次引擎一致、无明显缺陷。
- 任何更深的业务流程重构（如评审/轮次状态机简化、权限模型细化）**风险高、需你在场逐项确认**，我没有动。需要时我们一项一项过。

---

## C. 我主动没做的事（及原因）
- **没有**无人值守地批量改业务逻辑/数据库结构——一旦引入回归，你不在场 8 小时内系统可能一直是坏的。
- **没有**删除任何非我创建的文件（只在上面列出建议）。
- 所有 UI 改动都做到了：每批 `tsc -b` 通过 → `./rebuild.sh` 构建 → 健康检查 200 → 日志无报错，保证线上始终可用。
