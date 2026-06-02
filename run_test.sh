#!/usr/bin/env bash
# 测试实例：与正式服务(1573)并行运行，用于上线前验证。
#   端口 1574 · 数据库 pms.test.db(正式库副本) · 前端 frontend/dist-test
# 用法：
#   ./run_test.sh           启动/重启测试实例（首次自动从 pms.db 复制测试库）
#   ./run_test.sh --reset   重新从正式库 pms.db 复制一份测试库再启动
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
BACKEND="$ROOT/backend"
PORT=1574
TEST_DB="$ROOT/pms.test.db"
TEST_DIST="$FRONTEND/dist-test"
PYTHON="/home/huangxb/test/venv/bin/python"   # 与 rebuild.sh 一致
LOG="$BACKEND/server.test.log"

RESET=0
[ "${1:-}" = "--reset" ] && RESET=1

echo "==> [1/3] 准备测试数据库 (pms.test.db)"
if [ "$RESET" = "1" ] || [ ! -f "$TEST_DB" ]; then
  cp "$ROOT/pms.db" "$TEST_DB"
  echo "    已从正式库 pms.db 复制 -> pms.test.db"
else
  echo "    复用已有 pms.test.db（如需刷新请加 --reset）"
fi

echo "==> [2/3] 构建测试前端 (输出到 frontend/dist-test，不动正式 dist)"
cd "$FRONTEND"
npm run build -- --outDir dist-test --emptyOutDir

echo "==> [3/3] 停止旧测试后端 (端口 $PORT) 并启动新实例"
OLD_PID="$(ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+' | head -n1 || true)"
if [ -n "${OLD_PID:-}" ]; then
  echo "    结束旧进程 PID=$OLD_PID"
  kill "$OLD_PID" 2>/dev/null || true
  for _ in $(seq 1 10); do
    ss -ltn 2>/dev/null | grep -q ":$PORT " || break
    sleep 1
  done
else
  echo "    没有发现正在运行的测试后端"
fi

cd "$BACKEND"
PMS_PORT="$PORT" PMS_DB_PATH="$TEST_DB" PMS_DIST="$TEST_DIST" \
  nohup "$PYTHON" app.py > "$LOG" 2>&1 &
NEW_PID=$!

for _ in $(seq 1 15); do
  if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
    echo ""
    echo "✓ 测试实例已启动 (PID=$NEW_PID)，监听 http://0.0.0.0:$PORT"
    echo "  数据库：$TEST_DB"
    echo "  日志：  $LOG"
    echo "  正式服务(1573)不受影响。浏览器请强制刷新 (Ctrl+Shift+R)。"
    exit 0
  fi
  sleep 1
done

echo "✗ 测试后端可能启动失败，请查看日志：$LOG"
tail -n 20 "$LOG" || true
exit 1
