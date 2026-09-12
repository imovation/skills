#!/bin/bash
# Headscale 备份脚本（SQLite 在线安全备份，无需停服）
set -euo pipefail

BACKUP_DIR=/opt/headscale-backup
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

# SQLite 在线安全备份（自动合并 WAL）
sqlite3 /opt/headscale/data/db.sqlite ".backup '$BACKUP_DIR/db-$DATE.sqlite'"

# 配置 + 密钥 + compose（排除数据库及其 WAL/SHM 临时文件）
tar czf "$BACKUP_DIR/headscale-$DATE.tar.gz" \
  -C /opt \
  --exclude='headscale/data/db.sqlite*' \
  headscale/docker-compose.yml \
  headscale/config \
  headscale/data

chmod 600 "$BACKUP_DIR"/*.sqlite "$BACKUP_DIR"/*.tar.gz

# 保留最近 14 天
find "$BACKUP_DIR" \( -name '*.gz' -o -name '*.sqlite' \) -mtime +14 -delete

echo "[$(date '+%F %T')] backup ok: db-$DATE.sqlite + headscale-$DATE.tar.gz"
