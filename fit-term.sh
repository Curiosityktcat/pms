#!/bin/bash
# 网页终端内容缩在左上角/右边一条竖线 → 把 screen 窗口撑到当前最大 client 尺寸
# 用法: bash ~/pms/fit-term.sh [会话名，默认 pms]
S=${1:-pms}
echo -n "修复前: "; screen -S "$S" -Q info
screen -S "$S" -X fit
sleep 1
echo -n "修复后: "; screen -S "$S" -Q info; echo
echo '各 client 尺寸(行 列):'
for p in $(ls /dev/pts | grep -E '^[0-9]+$'); do printf '  pts/%s: ' $p; stty -F /dev/pts/$p size 2>/dev/null || echo -; done
