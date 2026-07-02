# PMS 服务器迁移指南（迁到另一台机器）

> 本文档由 Claude 于 2026-06 整理，覆盖把 `~/pms` 整套自行采购管理系统迁移到新机器所需的全部步骤、数据、依赖与需要改动的配置。按顺序执行即可。

---

## 0. 系统构成速览

- **后端**：Python / Flask（`backend/app.py`），SQLite 单库 `pms.db`，监听 `0.0.0.0:1573`。
- **前端**：React + Vite + antd，构建产物在 `frontend/dist`，由后端直接托管（同端口）。
- **数据**：全部在仓库根目录 `~/pms` 下的几个目录 + `pms.db`（见第 4 节）。
- **对外暴露**：cpolar 内网穿透（固定域名 `njyycgb.vip.cpolar.cn`）+ ttyd 网页终端 + hermes（QQ 机器人）。这些是**主机级基础设施**，不在仓库内，迁移时单独处理（见第 7 节）。
- **外部依赖（局域网）**：LLM 推理服务 `192.168.1.10:8888`、PaddleOCR `192.168.1.12:8118`。新机器需能访问同一局域网，否则相关功能（AI 编制建议、投标审查、文件识别）不可用，需改配置指向新地址。

---

## 1. 新机器前置要求

```bash
# 系统包
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nodejs npm git
# Node 建议 18+，npm 9+；如系统源版本过低用 nvm 或 nodesource 装新版
node -v && npm -v && python3 --version
```

## 2. 取代码

```bash
# 方式A：从 git 远端 clone（若有）
git clone <仓库地址> ~/pms
# 方式B：直接 rsync 整个目录（含数据），最省事：
#   rsync -avz --exclude node_modules --exclude '__pycache__' --exclude 'frontend/dist' \
#         旧机:~/pms/  ~/pms/
cd ~/pms
```

## 3. Python 后端

```bash
# 创建 venv（位置自定，但要同步改 rebuild.sh / run_test.sh 里的 PYTHON 变量，见第 7 节）
python3 -m venv ~/pms/venv
~/pms/venv/bin/pip install --upgrade pip
~/pms/venv/bin/pip install -r ~/pms/backend/requirements.txt

# Playwright 浏览器内核（开标看板/四川公告抓取需要）
~/pms/venv/bin/playwright install chromium
# 若缺系统库：~/pms/venv/bin/playwright install-deps  （或按报错装 libnss3 等）
```

> ⚠️ `rebuild.sh` **不会**自动 `pip install`。每次重建 venv 后都要手动跑上面两条，否则
> 归档一键打印（docxcompose）、抓取（playwright）等会报 ModuleNotFoundError。

## 4. 拷贝数据目录（**务必全部带上**）

这些都在 `~/pms` 根目录下，迁移时整目录复制（rsync 方式B已含）：

| 路径 | 内容 | 必须 |
|------|------|------|
| `pms.db` | **主数据库**（项目/合同/人员/聊天/全部业务数据，~32M） | ✅ |
| `uploads/` | 合同、采购结果、紧急采购、中标通知书等上传件 | ✅ |
| `询价附件/` | 询/议价函附件、模板、响应文件（~47M） | ✅ |
| `医院模板/` | 各类 Word 模板（13.2 模板维护管理的就是它） | ✅ |
| `身份证/` | 人员身份证照片（授权函要用） | ✅ |
| `聊天附件/` | 站内聊天图片/文件 | ✅ |
| `ocr_cache/` | OCR 结果缓存 | 可选（不带会重新识别） |

> 单据上传目录代码里多用 `os.path.join(__file__,...)` 相对定位，**保持目录结构不变**即可，无需改路径。
> 例外：私人文件库根目录默认 `/home/huangxb/files`（`PMS_FILEBOX_ROOT` 可覆盖），仅黄新博本人用，可不迁。

## 5. 构建前端 + 启动

```bash
cd ~/pms/frontend && npm install && npm run build   # 产出 frontend/dist
cd ~/pms/backend && ~/pms/venv/bin/python app.py     # 监听 0.0.0.0:1573
# 浏览器访问 http://<新机IP>:1573 验证
```

可用环境变量覆盖默认（一般不用改）：
- `PMS_PORT`（默认 1573）
- `PMS_DB_PATH`（默认 `~/pms/pms.db`）
- `PMS_DIST`（默认 `~/pms/frontend/dist`）
- `PMS_FILEBOX_ROOT`（默认 `/home/huangxb/files`）

一键重建脚本：`./rebuild.sh`（构建前端 + 重启后端）。

## 6. 需要在新机器上**改**的配置

1. **`rebuild.sh` 与 `run_test.sh`**：把 `PYTHON="/home/huangxb/test/venv/bin/python"` 改成新机 venv 路径（如 `~/pms/venv/bin/python`）。
2. **`backend/app.py` 的 `SECRET_KEY`**：当前硬编码为 `"change-this-secret-key-please"` —— 迁移时**务必换成随机强密钥**（否则会话可被伪造）。建议改成读环境变量：`os.environ.get("PMS_SECRET_KEY", "<随机串>")`。换 key 后所有人需重新登录。
3. **局域网外部服务地址**（若新机不在同一网段或服务搬家）：
   - LLM：`192.168.1.10:8888`（OpenAI 兼容 `/v1/chat/completions`）——在「13.4 抓取模型设置」页或 sys_config 表里改。
   - PaddleOCR：`192.168.1.12:8118`——文件识别用。
   - 这两个地址在代码/DB 配置里，确认新机能 ping 通；不通则相应功能降级。
4. **邮件发送**（询/议价函群发）：SMTP/IMAP 账号配置在「13.3 邮件设置」，存 DB，随 `pms.db` 一起迁，无需重配；但确认新机出网 25/465/993 端口可用。

## 7. 对外暴露与常驻服务（基础设施，按需迁）

这些不在仓库里，是主机级配置，迁移时参考旧机的 memory 笔记重建：
- **cpolar**：内网穿透，固定域名 `njyycgb.vip.cpolar.cn`。配置 `/usr/local/etc/cpolar/cpolar.yml`（subdomain=njyycgb, region=cn_vip, addr=1573）。账号 756325708@qq.com。
- **ttyd**：网页终端，user systemd `~/.config/systemd/user/ttyd.service`，端口 7681 + screen 会话。
- **hermes**：QQ 机器人网关，托管 cpolar 生命周期。
- **后端常驻**：建议在新机做成 systemd 服务（`ExecStart=~/pms/venv/bin/python ~/pms/backend/app.py`，`Environment=PMS_SECRET_KEY=...`），开机自启，替代手动 `nohup`。
- **swap**：旧机 7G 内存易 OOM，曾扩 swap 到 10G；新机内存若小也建议配 swap。

## 8. 迁移后验收清单

- [ ] `http://新机:1573` 能打开、能登录（admin 及业务账号）。
- [ ] 项目流程页能看到历史项目（证明 pms.db 生效）。
- [ ] 某项目「进展」「编辑」正常；合同/归档页有数据。
- [ ] 归档「一键打印资料」能生成 docx（证明 docxcompose 装好）。
- [ ] 生成一个 Word（如采购结果确认函）——证明 python-docx + 医院模板就位。
- [ ] 授权函能下载——证明身份证照片目录迁好。
- [ ] 开标看板/四川公告能抓取——证明 playwright + chromium 就位（不急可后验）。
- [ ] 文件识别能调 PaddleOCR、AI 建议能调 LLM——证明局域网服务可达。
- [ ] 登录会话稳定——确认已换 SECRET_KEY。

---

_依赖清单见 `backend/requirements.txt`；一键安装脚本见 `setup.sh`。_
