#!/usr/bin/env bash
# 把网页终端从 ttyd.service(裸 bash -l) 切到 webterm.service(screen -xRR cc)
# 目的: 刷新浏览器后重连同一个常驻 screen 会话, 不再丢失对话/正在运行的程序。
# 带自动回滚: 如果新服务起不来或 7681 没在监听, 自动滚回 ttyd.service, 保证不被锁在外面。
# 必须以 root 运行, 且应脱离当前终端(systemd-run)执行, 因为切换会断开当前网页终端连接。
set -u
LOG=/home/huangxb/pms/term-switch.log
exec >>"$LOG" 2>&1
echo "==================== switch start: $(date) ===================="

port_up() { ss -tlnp 2>/dev/null | grep -q ':7681 '; }

echo "[1/4] 停用并停止 ttyd.service (裸 bash 版本)"
systemctl disable --now ttyd.service

echo "[2/4] 启用并启动 webterm.service (screen 版本)"
systemctl enable webterm.service
systemctl restart webterm.service

echo "[3/4] 等待新服务就绪..."
for i in $(seq 1 10); do
  sleep 1
  if systemctl is-active --quiet webterm.service && port_up; then
    echo "[OK] webterm.service 已 active, 端口 7681 正在监听 (用了 ${i}s)"
    echo "==================== switch done OK: $(date) ===================="
    exit 0
  fi
done

echo "[4/4] !! 新服务未在 10s 内就绪, 执行回滚 -> ttyd.service"
systemctl disable --now webterm.service
systemctl enable --now ttyd.service
sleep 2
if port_up; then
  echo "[ROLLBACK OK] 已滚回 ttyd.service, 端口 7681 恢复监听。网页终端仍可用(但仍是不持久的旧版)。"
else
  echo "[ROLLBACK WARNING] 7681 仍未监听, 请手动检查: systemctl status ttyd.service webterm.service"
fi
echo "==================== switch end(rolled back): $(date) ===================="
exit 1
