#!/usr/bin/env bash
# 安全地把 swap 调整为 10G：先建新的挂上，再卸旧的，避免回灌内存触发 OOM
set -euo pipefail

NEW=/swap10g.img
OLD=/swap.img

echo "==> 1. 创建 10G 新 swap 文件"
fallocate -l 10G "$NEW"
chmod 600 "$NEW"
mkswap "$NEW"

echo "==> 2. 挂上新 swap（此时总量 14G，安全）"
swapon "$NEW"

echo "==> 3. 卸掉旧的 4G swap（3.4G 安全迁移到内存/新swap）"
swapoff "$OLD"
rm -f "$OLD"

echo "==> 4. 更新 /etc/fstab"
cp /etc/fstab /etc/fstab.bak.$(date +%s)
sed -i "s#^${OLD}[[:space:]].*#${NEW}\tnone\tswap\tsw\t0\t0#" /etc/fstab

echo "==> 完成。当前状态："
swapon --show
echo "---"
free -h
echo "--- fstab swap 行 ---"
grep swap /etc/fstab
