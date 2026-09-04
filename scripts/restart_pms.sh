#!/usr/bin/env bash
# 重启 PMS 并**核对进程真的换了**。
#
# 教训（2026-09-03）：改完代码跑了 systemctl restart，只看 `systemctl is-active`
# 说 active 就当上线了——可 is-active 在没重启时也一直是 active。结果生产上
# 连着两次跑的都是旧代码，用户看到的还是修好之前的老毛病。
# 判据只有一个：MainPID 变了、且新进程的启动时间晚于代码文件的改动时间。
set -u
SVC=${1:-pms.service}
OLD=$(systemctl show "$SVC" -p MainPID --value)
echo "旧 PID: $OLD"

# ssh 里没有 tty，sudo 拿不到密码也存不住凭据（tty_tickets），
# 所以先试免密，不行就从标准输入读一行密码：`echo <pw> | bash restart_pms.sh`
if ! sudo -n systemctl restart "$SVC" 2>/dev/null; then
  if [ -t 0 ]; then
    sudo systemctl restart "$SVC" || { echo "重启命令失败"; exit 1; }
  else
    sudo -S systemctl restart "$SVC" 2>/dev/null \
      || { echo "重启命令失败（需要 sudo 密码：echo <密码> | bash $0）"; exit 1; }
  fi
fi

for _ in $(seq 1 20); do
  NEW=$(systemctl show "$SVC" -p MainPID --value)
  [ -n "$NEW" ] && [ "$NEW" != "0" ] && [ "$NEW" != "$OLD" ] && break
done

if [ "$NEW" = "$OLD" ] || [ -z "$NEW" ] || [ "$NEW" = "0" ]; then
  echo "！PID 没变（还是 $OLD）——服务没有真的重启，别当已上线"
  exit 1
fi

STARTED=$(systemctl show "$SVC" -p ActiveEnterTimestamp --value)
echo "新 PID: $NEW"
echo "启动时间: $STARTED"

# 新进程必须晚于代码：不然重启的还是改动前的那份
NEWEST=$(find /home/huangxb/pms/backend -name '*.py' -newermt "$STARTED" -print -quit 2>/dev/null)
if [ -n "$NEWEST" ]; then
  echo "！有代码比进程还新：$NEWEST —— 再重启一次"
  exit 1
fi

# 起来要几秒（建表、补列、回填都在启动时跑），别一重启就判死刑
CODE=000
for _ in $(seq 1 30); do
  CODE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://127.0.0.1:1573/ || echo 000)
  [ "$CODE" = "200" ] && break
  sleep 1
done
echo "首页: $CODE"
[ "$CODE" = "200" ] || { echo "！首页起不来，看 journalctl -u $SVC -n 50"; exit 1; }
echo "上线核对通过"
