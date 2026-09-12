#!/bin/bash
# 用 NPM API 申请 Let's Encrypt 证书并创建 Synapse 反向代理
# 用法: ./setup-ssl.sh <域名> <NPM管理员密码>
set -e
DOMAIN="${SYNAPSE_SERVER_NAME:-$1}"
ADMIN_EMAIL="admin@${DOMAIN}"
NPM_PASS="$2"

if [ -z "$DOMAIN" ] || [ -z "$NPM_PASS" ]; then
  echo "用法: $0 <域名> <NPM管理员密码>"
  exit 1
fi

echo "=== 登录 NPM ==="
TOKEN=$(curl -s -X POST http://localhost:81/api/tokens \
  -H "Content-Type: application/json" \
  -d "{\"identity\":\"${ADMIN_EMAIL}\",\"secret\":\"${NPM_PASS}\"}" | jq -r '.token // empty')

if [ -z "$TOKEN" ]; then
  echo "登录失败，请检查 NPM 管理员邮箱和密码"
  exit 1
fi

echo "=== 申请 Let's Encrypt 证书 ==="
CERT_RESULT=$(curl -s -X POST http://localhost:81/api/nginx/certificates \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider\":\"letsencrypt\",\"domain_names\":[\"${DOMAIN}\"],\"meta\":{\"dns_challenge\":false}}")

CERT_ID=$(echo "$CERT_RESULT" | jq -r '.id // empty')
if [ -z "$CERT_ID" ]; then
  echo "证书申请失败:"
  echo "$CERT_RESULT" | jq .
  exit 1
fi

echo "=== 创建反向代理 ==="
PROXY_RESULT=$(curl -s -X POST http://localhost:81/api/nginx/proxy-hosts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"domain_names\":[\"${DOMAIN}\"],\"forward_scheme\":\"http\",\"forward_host\":\"synapse\",\"forward_port\":8008,\"certificate_id\":${CERT_ID},\"ssl_forced\":true,\"http2_support\":true,\"allow_websocket_upgrade\":true,\"hsts_enabled\":true,\"block_exploits\":true,\"trust_forwarded_proto\":true,\"enabled\":true}")

PROXY_ID=$(echo "$PROXY_RESULT" | jq -r '.id // empty')
if [ -z "$PROXY_ID" ]; then
  echo "代理创建失败:"
  echo "$PROXY_RESULT" | jq .
  exit 1
fi

echo "部署完成！访问 https://${DOMAIN}"
