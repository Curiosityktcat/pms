#!/usr/bin/env bash
# 重置 PMS admin 账号密码（密码由你在命令行给定）。
# 用法：  bash ~/pms/reset-admin-pw.sh '你的新密码'
set -euo pipefail
if [ $# -lt 1 ] || [ -z "${1:-}" ]; then
  echo "用法: bash $0 '你的新密码'"; exit 1
fi
cd /home/huangxb/pms/backend
NEW_PW="$1" /home/huangxb/pms/venv/bin/python - <<'PY'
import os, hashlib, secrets
from app import create_app
from models import db
from models.user import User

pw = os.environ["NEW_PW"]
app = create_app()
with app.app_context():
    u = db.session.execute(db.select(User).filter_by(username="admin")).scalar_one_or_none()
    if not u:
        print("❌ 未找到 admin 账号"); raise SystemExit(1)
    salt = secrets.token_hex(16)
    u.salt = salt
    u.pw_hash = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200000).hex()
    u.active = 1
    db.session.commit()
    print("✅ admin 密码已重置，现在可用新密码登录（登录即时生效，无需重启）")
PY
