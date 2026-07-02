#!/usr/bin/env bash
set -euo pipefail

sudo tee /etc/systemd/system/cloudflared-pms.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel for PMS (pms.curiosityktcat.cn -> localhost:1573)
After=network-online.target pms.service
Wants=network-online.target

[Service]
User=huangxb
ExecStartPre=/bin/sleep 15
ExecStart=/home/huangxb/.local/bin/cloudflared tunnel --no-autoupdate --config /home/huangxb/.cloudflared/config.yml run pms
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
echo "✓ 完成，下次重启 cloudflared 将延迟 15 秒启动"
