#!/usr/bin/env bash
# 一键修复网页终端(ttyd + screen)无法滚轮回看历史的问题。
# 用法：  sudo bash ~/pms/fix-webterm-scroll.sh
# 说明：需要 root（改 systemd 单元 + 重启服务）。脚本结尾会重启 pms 会话，
#       当前 Claude Code 进程会被结束，重连网页后用 /resume 即可接回对话。
set -euo pipefail

USER_NAME=huangxb
HOME_DIR=/home/${USER_NAME}
UNIT=/etc/systemd/system/ttyd.service

if [ "$(id -u)" -ne 0 ]; then
  echo "请用 sudo 运行： sudo bash $0" >&2
  exit 1
fi

echo "==> [1/4] 写入 ${HOME_DIR}/.screenrc（加大回看 + 关闭备用屏幕，让滚轮能滚）"
cat > "${HOME_DIR}/.screenrc" <<'EOF'
# 回看缓冲行数
defscrollback 100000
# 关键：不让 screen 占用终端备用屏幕，这样 ttyd 滚轮/Shift+滚轮能直接滚回看历史
termcapinfo xterm* ti@:te@
EOF
chown "${USER_NAME}:${USER_NAME}" "${HOME_DIR}/.screenrc"

echo "==> [2/4] 给 ttyd.service 增加 scrollback=100000（幂等）"
if grep -q 'scrollback=' "$UNIT"; then
  echo "    已存在 scrollback 选项，跳过。"
else
  sed -i 's/\(-t fontSize=15 \\\)/\1\n    -t scrollback=10000 \\/' "$UNIT"
  echo "    已插入。"
fi
systemctl daemon-reload

echo "==> [3/4] 给运行中的 pms 会话即时加大缓冲"
sudo -u "${USER_NAME}" screen -S pms -X defscrollback 100000 2>/dev/null || true

echo "==> [4/4] 2 秒后重启 pms 会话 + ttyd（网页会断开重连；重连后用 /resume 接回对话）"
nohup bash -c "sleep 2; sudo -u '${USER_NAME}' screen -S pms -X quit 2>/dev/null; systemctl restart ttyd.service" \
  >/tmp/fix-webterm-scroll-restart.log 2>&1 &

echo "完成：配置已就绪，正在后台重启。请稍候刷新/重连网页终端，然后输入 /resume。"
