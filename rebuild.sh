#!/usr/bin/env bash
# 一键重建：构建前端 dist + 重启后端（端口 1573）
# 优先用 systemd（pms.service）重启；无该单元时回退到 nohup 直起方式。
# 用法：  ./rebuild.sh        # systemd 路径会用 sudo 重启服务，按提示输密码
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$ROOT/frontend"
BACKEND="$ROOT/backend"
PORT=1573
LOG="$BACKEND/server.log"
SERVICE="pms.service"

# Python 解释器（仅 nohup 回退路径用）：优先 PMS_PYTHON，其次仓库内 venv，最后旧机默认路径
if [ -n "${PMS_PYTHON:-}" ]; then
  PYTHON="$PMS_PYTHON"
elif [ -x "$ROOT/venv/bin/python" ]; then
  PYTHON="$ROOT/venv/bin/python"
else
  PYTHON="/home/huangxb/test/venv/bin/python"
fi

# 会话密钥：持久化在 .pms_secret_key（systemd 与 nohup 都从此文件读取）
# 首次自动生成强随机；已存在则不动（重启不掉登录）。已 gitignore。
SECRET_FILE="$ROOT/.pms_secret_key"
if [ ! -s "$SECRET_FILE" ]; then
  ( umask 077; { openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; } > "$SECRET_FILE" )
  echo "    已生成会话密钥 .pms_secret_key（本次重启后所有人需重新登录）"
fi

echo "==> [1/2] 构建前端 (npm run build)"
cd "$FRONTEND"
npm run build

# ── 判断后端托管方式 ────────────────────────────────────────────────
if command -v systemctl >/dev/null 2>&1 && systemctl cat "$SERVICE" >/dev/null 2>&1; then
  echo "==> [2/2] 通过 systemd 重启后端 ($SERVICE，需 sudo)"
  sudo systemctl restart "$SERVICE"
  for _ in $(seq 1 15); do
    if ss -ltn 2>/dev/null | grep -q ":$PORT "; then
      echo ""
      echo "✓ 重建完成，$SERVICE 已重启，监听 http://0.0.0.0:$PORT"
      echo "  日志：journalctl -u $SERVICE -f"
      echo "  浏览器请强制刷新 (Ctrl+Shift+R) 以加载新前端。"
      exit 0
    fi
    sleep 1
  done
  echo "✗ 重启后端口 $PORT 未监听，请查看：journalctl -u $SERVICE -n 50"
  exit 1
fi

# ── 回退：无 systemd 单元，nohup 直起 ───────────────────────────────
echo "==> [2/2] 未发现 systemd 单元 $SERVICE，回退到 nohup 直起方式"
export PMS_SECRET_KEY="$(cat "$SECRET_FILE")"

echo "    停止旧后端 (端口 $PORT)"
# 收集监听该端口的进程（grep 无匹配返回 1，用 || true 防 pipefail 误伤）
OLD_PIDS="$( { ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+'; } 2>/dev/null | sort -u | tr '\n' ' ' || true)"
# 兜底：揪出所有 backend/app.py 进程（即使没监听端口的僵尸/孤儿）
STRAY="$( { pgrep -f "$BACKEND/app.py" 2>/dev/null; ps -eo pid,args 2>/dev/null | grep -E '[p]ython.* app\.py' | awk '{print $1}'; } | sort -u | tr '\n' ' ' || true)"
ALL_PIDS="$(echo "$OLD_PIDS $STRAY" | tr ' ' '\n' | sort -u | tr '\n' ' ')"
if [ -n "${ALL_PIDS// /}" ]; then
  echo "    结束旧进程 PID: $ALL_PIDS"
  kill $ALL_PIDS 2>/dev/null || true
  for _ in $(seq 1 10); do
    ss -ltn 2>/dev/null | grep -q ":$PORT " || break
    sleep 1
  done
  STILL="$( { ss -ltnp 2>/dev/null | grep ":$PORT " | grep -oP 'pid=\K[0-9]+'; } 2>/dev/null | sort -u | tr '\n' ' ' || true)"
  if [ -n "${STILL// /}" ]; then
    echo "    端口仍被占用，强杀 PID: $STILL"
    kill -9 $STILL 2>/dev/null || true
    sleep 2
  fi
else
  echo "    没有发现正在运行的后端"
fi

echo "    启动后端 ($PYTHON app.py)"
cd "$BACKEND"
nohup "$PYTHON" app.py > "$LOG" 2>&1 &
NEW_PID=$!
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
