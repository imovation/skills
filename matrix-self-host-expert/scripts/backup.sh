#!/bin/bash
# Matrix/Synapse 备份脚本：数据库 dump + 配置/密钥/.env 打包
set -euo pipefail

BACKUP_DIR="/root/matrix-backup"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

docker exec matrix-db pg_dump -U synapse synapse | gzip > \
  "$BACKUP_DIR/synapse-db-${DATE}.sql.gz"

tar czf "$BACKUP_DIR/synapse-config-${DATE}.tar.gz" \
  /root/matrix/synapsedata/homeserver.yaml \
  /root/matrix/synapsedata/*.signing.key \
  /root/matrix/.env

# 保留最近 7 天
find "$BACKUP_DIR" -name "*.gz" -mtime +7 -delete
echo "备份完成: $BACKUP_DIR"
