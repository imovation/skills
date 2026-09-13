#!/bin/bash
# 同步机场订阅到服务器的 mihomo。
# 用法：把本脚本放在 ~/.local/bin/，然后配 cron；服务器与订阅 URL 见下方变量。
# 安全：订阅 URL（含 token）存 ~/.config/mihomo-sync/sub-url（chmod 600），脚本运行时读取。

set -euo pipefail

SUB_URL_FILE="$HOME/.config/mihomo-sync/sub-url"
SSHKEY="$HOME/.ssh/id_ed25519_sync"
SRV="root@<SERVER_IP>"
LOCAL_PROXY_PORT=7897

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

[ -f "$SUB_URL_FILE" ] || { echo "missing $SUB_URL_FILE"; exit 1; }
URL="$(cat "$SUB_URL_FILE")"

# 优先经本机 clash 抓订阅，失败则直连兜底
if ! /usr/bin/curl -fsSL --proxy "http://127.0.0.1:${LOCAL_PROXY_PORT}" -m 60 -o "$TMP/raw.yaml" "$URL"; then
  /usr/bin/curl -fsSL -m 60 -o "$TMP/raw.yaml" "$URL" || { echo "fetch failed"; exit 1; }
fi

# 归一化：订阅更新会把 port/controller/secret/dns 覆写回机场默认，必须每回重刷
/usr/bin/python3 - "$TMP/raw.yaml" "$TMP/config.yaml" <<'PY'
import re, sys
src, out = sys.argv[1], sys.argv[2]
txt = open(src, errors='replace').read()
txt = re.sub(r'(?m)^mixed-port: .*', 'mixed-port: 7897', txt)
txt = re.sub(r"(?m)^external-controller: .*", "external-controller: '127.0.0.1:9090'", txt)
txt = re.sub(r"(?m)^secret: .*", "secret: '<SAME_RANDOM_SECRET_AS_DEPLOY>'", txt)
txt = re.sub(r"(?m)^  listen: .*", "  listen: '127.0.0.1:53'", txt)
open(out, 'w').write(txt)
PY

/usr/bin/scp -i "$SSHKEY" -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new \
  "$TMP/config.yaml" "$SRV:/etc/mihomo/config.yaml"

/usr/bin/ssh -i "$SSHKEY" -o ConnectTimeout=20 "$SRV" \
  'systemctl restart mihomo && sleep 4 && systemctl is-active mihomo && \
   curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 20 -w "verify opencode.ai=%{http_code}\n" https://opencode.ai'

echo "sync ok: $(date '+%F %T')"