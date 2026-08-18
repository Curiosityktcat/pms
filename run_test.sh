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
LOG="$BACKEND/server.test.log"

# Python 解释器：与 rebuild.sh 一致（PMS_PYTHON > 仓库 venv > 旧机默认）
if [ -n "${PMS_PYTHON:-}" ]; then
  PYTHON="$PMS_PYTHON"
elif [ -x "$ROOT/venv/bin/python" ]; then
  PYTHON="$ROOT/venv/bin/python"
else
  PYTHON="/home/huangxb/test/venv/bin/python"
fi

RESET=0
[ "${1:-}" = "--reset" ] && RESET=1

echo "==> [1/3] 准备测试数据库 (pms.test.db)"
if [ "$RESET" = "1" ] || [ ! -f "$TEST_DB" ]; then
  # 正式库正被 1573 的 gunicorn 写着，**不能 cp**：拷出来的往往缺 WAL 里的内容，
  # 起来就报 "malformed database schema"（2026-08-18 实测踩到）。
  # 用 sqlite 的在线备份 API，它会正确地把 WAL 一起合进去。
  rm -f "$TEST_DB" "$TEST_DB"-wal "$TEST_DB"-shm
  "$PYTHON" - "$ROOT/pms.db" "$TEST_DB" <<'PYBACKUP'
import sqlite3, sys
src = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True)
dst = sqlite3.connect(sys.argv[2])
src.backup(dst)
dst.close(); src.close()
PYBACKUP
  echo "    已从正式库 pms.db 在线备份 -> pms.test.db"
else
  echo "    复用已有 pms.test.db（如需刷新请加 --reset）"
fi

echo "==> [2/3] 构建测试前端 (输出到 frontend/dist-test，不动正式 dist)"
cd "$FRONTEND"
VITE_PMS_ENV=test npm run build -- --outDir dist-test --emptyOutDir

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
