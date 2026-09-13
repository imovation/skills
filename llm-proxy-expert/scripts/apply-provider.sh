#!/bin/bash
# 服务器侧：接收本机推送的 provider 文件，校验 → 备份 → 原子替换 → API 热重载 → 走代理验证，失败自动回滚。
# 运行在服务器 root 下；本机用 forced-command 的 id_ed25519_sync 触发（stdin 无密码，凭据不出服务器）。
# 部署：install -m 0755 apply-provider.sh /usr/local/bin/apply-provider.sh
# 前置：/etc/mihomo/config.yaml 已用 proxy-providers 引用 ./providers/airport.yaml，
#       /etc/mihomo/.controller_secret(chmod 600) 存管理员 secret。

set -euo pipefail

STAGE="${1:?usage: apply-provider.sh <staged-file>}"
PROVIDER_DIR="/etc/mihomo/providers"
NAME="airport"
LIVE="$PROVIDER_DIR/$NAME.yaml"
BAK_DIR="$PROVIDER_DIR/.bak"
SECRET_FILE="/etc/mihomo/.controller_secret"
CTRL="127.0.0.1:9090"
MIN_NODES=3

[ -s "$STAGE" ] || { echo "empty staging: $STAGE"; exit 2; }

# 1) 节点数下限校验（防空订阅/报错页覆盖线上）
NODES="$(python3 - "$STAGE" <<'PY'
import sys, yaml
print(len((yaml.safe_load(open(sys.argv[1])) or {}).get('proxies') or []))
PY
)"
[ "$NODES" -ge "$MIN_NODES" ] || { echo "too few nodes=$NODES"; exit 3; }

# 2) 备份 + 原子替换
mkdir -p "$BAK_DIR"
[ -f "$LIVE" ] && cp -a "$LIVE" "$BAK_DIR/$NAME.yaml.$(date +%Y%m%dT%H%M%S)"
install -m 0644 "$STAGE" "$LIVE"

# 3) 清理旧备份（保留最近 7 份）
ls -1t "$BAK_DIR/$NAME.yaml."* 2>/dev/null | tail -n +8 | xargs -r rm -f --

SECRET="$(cat "$SECRET_FILE")"

reload() {
  curl -s -o /dev/null -w '%{http_code}' -X PUT "http://$CTRL/providers/proxies/$NAME" \
    -H "Authorization: Bearer $SECRET"
}

rollback() {
  LATEST="$(ls -1t "$BAK_DIR/$NAME.yaml."* 2>/dev/null | head -1)"
  [ -n "$LATEST" ] || return 1
  install -m 0644 "$LATEST" "$LIVE"
  reload >/dev/null || true
}

# 4) 热重载 provider（不断整进程的连接）
CODE="$(reload)"
if [ "$CODE" != "200" ] && [ "$CODE" != "204" ]; then
  echo "reload failed ($CODE), rolling back"
  rollback || true
  exit 4
fi

# 5) 热重载后走代理端到端验证
CODE="$(curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 20 -w '%{http_code}' https://opencode.ai)"
if [ "$CODE" != "200" ]; then
  echo "egress verify failed ($CODE), rolling back"
  rollback || true
  exit 5
fi

echo "provider $NAME applied: nodes=$NODES, opencode.ai=200"