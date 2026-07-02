#!/usr/bin/env bash
set -euo pipefail

sudo tee /etc/systemd/system/ttyd.service > /dev/null << 'EOF'
[Unit]
Description=ttyd 网页终端 (port 7681)
After=network-online.target
Wants=network-online.target

[Service]
User=huangxb
EnvironmentFile=/home/huangxb/.ttyd.env
Environment=TERM=xterm-256color LANG=en_US.UTF-8
ExecStart=/usr/bin/ttyd \
    -p 7681 \
    -c ${TTYD_CREDS} \
    -P 30 -W \
    -t titleFixed=PMS终端 \
    -t fontSize=15 \
    bash -lc "cd /home/huangxb/pms; exec screen -xRR pms"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl restart ttyd
echo "✓ ttyd 已重启，刷新后会重连同一个 screen 会话（session 名: pms）"
