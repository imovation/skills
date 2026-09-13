#!/bin/bash
# 本机侧：拉取机场订阅 → 转 provider 格式 → 推送服务器 → 触发服务器侧 apply-provider.sh。
# 用法：放在 ~/.local/bin/，配 cron；服务器与订阅 URL 见下方变量。
# 安全：订阅 URL（含 token）存 ~/.config/mihomo-sync/sub-url（chmod 600），脚本运行时读取。
# 服务器侧脚本 apply-provider.sh 负责校验/原子替换/热重载/回滚/验证，本脚本只负责拉与推。

set -euo pipefail

SUB_URL_FILE="$HOME/.config/mihomo-sync/sub-url"
SSHKEY="$HOME/.ssh/id_ed25519_sync"
SRV="root@<SERVER_IP>"
LOCAL_PROXY_PORT=7897
STAGE="/tmp/airport.provider.yaml"   # 服务器首次应用前的 staging 路径（不直接覆盖线上）
MIN_NODES=3

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$SUB_URL_FILE" ] || { echo "missing $SUB_URL_FILE"; exit 1; }
URL="$(cat "$SUB_URL_FILE")"

# 1) 拉订阅（优先经本机 clash，失败则直连兜底）
if ! /usr/bin/curl -fsSL --proxy "http://127.0.0.1:${LOCAL_PROXY_PORT}" -m 60 -o "$TMP/raw.yaml" "$URL"; then
  /usr/bin/curl -fsSL -m 60 -o "$TMP/raw.yaml" "$URL" || { echo "fetch failed"; exit 1; }
fi

# 2) 转 provider 格式：只保留顶层 proxies，统一产出（服务器零转换逻辑）
/usr/bin/python3 - "$TMP/raw.yaml" "$TMP/provider.yaml" <<'PY'
import sys, yaml
src, out = sys.argv[1], sys.argv[2]
d = yaml.safe_load(open(src, encoding='utf-8', errors='replace')) or {}
proxies = d.get('proxies') or d.get('Proxy') or []
assert isinstance(proxies, list) and proxies, 'no proxies in subscription'
with open(out, 'w', encoding='utf-8') as f:
    yaml.safe_dump({'proxies': proxies}, f, allow_unicode=True, sort_keys=False)
print('nodes=%d' % len(proxies))
PY

# 3) 本地基础校验（防空中订阅/报错页覆盖好配置）
NODES="$(/usr/bin/python3 - "$TMP/provider.yaml" <<'PY'
import sys, yaml
print(len((yaml.safe_load(open(sys.argv[1])) or {}).get('proxies') or []))
PY
)"
[ "$NODES" -ge "$MIN_NODES" ] || { echo "too few nodes=$NODES"; exit 1; }

# 4) 推送到 staging 并触发服务器侧原子应用 + 热重载（forced-command 密钥只允许跑 apply-provider.sh）
/usr/bin/scp -i "$SSHKEY" -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new \
  "$TMP/provider.yaml" "$SRV:$STAGE"

/usr/bin/ssh -i "$SSHKEY" -o ConnectTimeout=20 -o BatchMode=yes "$SRV" -- "$STAGE"

echo "sync ok: $(date '+%F %T') nodes=$NODES"