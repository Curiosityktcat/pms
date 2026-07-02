#!/usr/bin/env bash
# PMS 新机器一键安装脚本（配合 MIGRATION.md 使用）
# 用法：先把整个 ~/pms 目录（含 pms.db 与各数据目录）拷到新机，再在 ~/pms 下执行 ./setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$ROOT/venv"

echo "==> [1/4] 创建 Python venv 并安装后端依赖"
if [ ! -d "$VENV" ]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install --upgrade pip
"$VENV/bin/pip" install -r "$ROOT/backend/requirements.txt"

echo "==> [2/4] 安装 Playwright Chromium 内核（抓取功能需要）"
"$VENV/bin/playwright" install chromium || echo "    [警告] chromium 安装失败，抓取功能不可用，可稍后重试"

echo "==> [3/4] 构建前端"
cd "$ROOT/frontend"
npm install
npm run build

echo "==> [4/4] 自检数据是否就位"
for f in pms.db 医院模板 询价附件; do
  [ -e "$ROOT/$f" ] && echo "    ✓ $f" || echo "    ✗ 缺少 $f（从旧机拷过来！见 MIGRATION.md 第4节）"
done

cat <<EOF

==> 安装完成。后续：
  1) 改 rebuild.sh / run_test.sh 里的 PYTHON= 为：$VENV/bin/python
  2) 设置会话密钥（强烈建议）：export PMS_SECRET_KEY=\$(openssl rand -hex 32)
  3) 启动后端：  $VENV/bin/python $ROOT/backend/app.py
     或一键重建：./rebuild.sh
  4) 浏览器访问 http://<本机IP>:1573 验收（清单见 MIGRATION.md 第8节）
EOF
