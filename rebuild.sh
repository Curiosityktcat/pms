#!/usr/bin/env bash
# 一键重建：构建前端 dist + 重启后端服务（端口 1573）
# 用法：  ./rebuild.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
BACKEND="$ROOT/backend"
PORT=1573
PYTHON="/home/huangxb/test/venv/bin/python"   # 后端使用的 Python 解释器
LOG="$BACKEND/server.log"

echo "==> [1/3] 构建前端 (npm run build)"
cd "$FRONTEND"
npm run build

echo "==> [2/3] 停止旧后端 (端口 $PORT)"
# 找到监听该端口的进程并结束
OLD_PID="$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | head -n1 || true)"
if [ -n "${OLD_PID:-}" ]; then
  echo "    结束旧进程 PID=$OLD_PID"
  kill "$OLD_PID" 2>/dev/null || true
  # 等待端口释放（最多 10 秒）
  for _ in $(seq 1 10); do
    ss -ltn 2>/dev/null | grep -q ":$PORT " || break
    sleep 1
  done
else
  echo "    没有发现正在运行的后端"
fi

echo "==> [3/3] 启动后端 ($PYTHON app.py)"
cd "$BACKEND"
nohup "$PYTHON" app.py > "$LOG" 2>&1 &
NEW_PID=$!

# 等待服务监听端口（最多 15 秒）
for _ in $(seq 1 15); do
  if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
    echo ""
    echo "✓ 重建完成，后端已启动 (PID=$NEW_PID)，监听 http://0.0.0.0:$PORT"
    echo "  日志：$LOG"
    echo "  浏览器请强制刷新 (Ctrl+Shift+R) 以加载新前端。"
    exit 0
  fi
  sleep 1
done

echo "✗ 后端可能启动失败，请查看日志：$LOG"
tail -n 20 "$LOG" || true
exit 1
