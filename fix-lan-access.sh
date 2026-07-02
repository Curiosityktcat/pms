#!/usr/bin/env bash
set -euo pipefail

# 1. nginx: 8090 改为局域网可访问
sudo tee /etc/nginx/sites-enabled/claude > /dev/null << 'EOF'
server {
    listen 8090;
    location / {
        auth_basic "claude";
        auth_basic_user_file /etc/nginx/.htpasswd-claude;
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;
        proxy_read_timeout 3600s;
    }
}
EOF
sudo nginx -t && sudo systemctl reload nginx
echo "✓ nginx (8090) 已改为 0.0.0.0"

# 2. ttyd: 去掉 -i lo 限制
sudo tee /etc/systemd/system/ttyd.service > /dev/null << 'EOF'
[Unit]
Description=ttyd 网页终端 (port 7681)
After=network-online.target
Wants=network-online.target

[Service]
User=huangxb
EnvironmentFile=/home/huangxb/.ttyd.env
ExecStart=/usr/bin/ttyd \
    -p 7681 \
    -c ${TTYD_CREDS} \
    -P 30 -W \
    -t titleFixed=PMS终端 \
    -t fontSize=15 \
    bash -l
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
echo "✓ ttyd.service 已去掉 -i lo"

# 3. svc-web: Flask 绑定改为 0.0.0.0
sed -i 's/host="127\.0\.0\.1"/host="0.0.0.0"/' /home/huangxb/svc-web/app.py
echo "✓ svc-web app.py 绑定改为 0.0.0.0"

# 4. 顺手禁用冲突的 webterm.service（和 ttyd 抢 7681 端口）
sudo systemctl disable --now webterm.service 2>/dev/null || true
echo "✓ webterm.service 已禁用（与 ttyd 冲突）"

# 5. 重载 + 重启
sudo systemctl daemon-reload
sudo systemctl restart ttyd svc-web

echo ""
echo "完成！局域网访问地址："
IP=$(ip addr show | grep "inet " | grep -v 127 | grep -v 198.18 | awk '{print $2}' | cut -d/ -f1 | head -1)
echo "  llama/claude 聊天: http://${IP}:8090"
echo "  网页终端:          http://${IP}:7681"
echo "  服务管理面板:      http://${IP}:9091"
