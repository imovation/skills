---
name: matrix-self-host-expert
description: 专门用于在 Linux 服务器上自动化部署和维护私有 Matrix (Synapse) 通信基座。当用户需要部署 Matrix 服务器、配置 HTTPS 反向代理、创建用户、处理 "M_LIMIT_EXCEEDED" / 数据库 locale 冲突 / ConfigError 等错误，或需要 Federation / TURN / 备份恢复等生产级运维时，务必使用此 Skill。涵盖 Docker compose 编排、NPM API 自动配置 SSL、Postgres 维护等完整工作流。
---

# Matrix 自建专家 (Matrix Self-Host Expert)

在 Ubuntu/Debian 服务器上构建生产级 Matrix (Synapse) 通信环境，专为国内环境优化。

本文件是主流程；部署模板在 `assets/`，可执行脚本在 `scripts/`，专项配置在 `references/`，需要时再读。

## 0. 前置准备

### 系统要求
| 规格 | 建议 |
|------|------|
| CPU | 2 核起，每 100 活跃用户 +1 核 |
| 内存 | 4G 起，每 100 活跃用户 +2G |
| 磁盘 | 20G 起，消息与媒体文件增长较快 |
| OS | Ubuntu 24.04 / 22.04 |

### 域名与 DNS
```bash
# 获取服务器公网 IP
curl -s ifconfig.me

# 确认域名已解析到该 IP
dig +short <你的域名>
```

### 端口全景
| 端口 | 用途 | 云安全组 | 说明 |
|------|------|---------|------|
| 80 | ACME HTTP 验证 | ✅ 放行 | Let's Encrypt 验证必需 |
| 443 | HTTPS 服务 | ✅ 放行 | Element / API 访问入口 |
| 81 | NPM 管理面板 | 限制来源 IP | 默认管理员 admin@<域名> |
| 8008 | Synapse 内部服务 | ❌ 不放行 | NPM 通过 Docker 内网访问 |
| 8448 | Federation | 按需放行 | 跨服务器联邦通信 |

> 部署前务必在云平台安全组放行 80/443，并用 `curl -s http://<域名>` 验证可达。
> 若无法放行 80，可改用 DNS Challenge 申请证书。

---

## 1. 安装 Docker

```bash
# 方案 A（官方脚本）
curl -fsSL https://get.docker.com -o /tmp/get-docker.sh && sh /tmp/get-docker.sh

# 方案 B（apt 后备，脚本被阻断时使用）
apt update && apt install -y docker.io docker-compose-v2

docker --version && docker compose version
```

### 配置国内镜像加速

```bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://dockerproxy.cn",
    "https://docker.agsv.top",
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io"
  ],
  "log-driver": "json-file",
  "log-opts": { "max-size": "50m", "max-file": "3" }
}
EOF
systemctl daemon-reload && systemctl restart docker
docker info | grep -A 2 "Registry Mirrors"
```

---

## 2. 目录与权限

```bash
mkdir -p /root/matrix/{synapsedata,postgresdata,npmdata,npmletsencrypt}
chown -R 991:991 /root/matrix/synapsedata
```

> Synapse 容器内用户 UID=991，用 `chown` 而非 `chmod 777`。

---

## 3. Docker Compose 与服务栈

```bash
cd /root/matrix
cp <skill目录>/assets/docker-compose.yml ./
cp <skill目录>/assets/.env.example .env
# 编辑 .env：域名、两个随机密码（openssl rand -base64 24 生成）
```

### 版本固定策略

- `SYNAPSE_IMAGE` 在 `.env` 中固定（默认 `matrixdotorg/synapse:v1.154.0`），升级只改 `.env`，不动 compose 文件。
- `NPM_IMAGE` 默认 `latest`，上线后从面板「关于」页查到实际版本再固定，避免 `latest` 漂移。
- `postgres:14-alpine` 固定大版本，不跨大版本自动升级。

### 关键设计

- Synapse 的 8008 只绑 `127.0.0.1`，对外统一走 NPM。
- `db` 带 healthcheck，Synapse `depends_on: condition: service_healthy`，避免首次启动连不上 DB。
- Synapse 容器显式传入 `POSTGRES_PASSWORD`，供 `homeserver.yaml` 里的 `${POSTGRES_PASSWORD}` 环境变量替换使用。
- 默认网络固定命名为 `matrix_default`，TURN 容器按此名接入（见 `references/turn.md`）。

---

## 4. Synapse 配置

### 生成初始配置

```bash
docker run --rm -v /root/matrix/synapsedata:/data \
  -e SYNAPSE_SERVER_NAME=<你的域名> \
  -e SYNAPSE_REPORT_STATS=no \
  matrixdotorg/synapse:v1.154.0 generate
```

### homeserver.yaml 必改项

把 `assets/homeserver-snippets.yaml` 中的块合并进 `/root/matrix/synapsedata/homeserver.yaml`。最重要的几项及原因：

- `database`（psycopg2 + `allow_unsafe_locale: true`）：不切 Postgres 会一直用 SQLite；不加该字段在非 C locale 的库上会报 `IncorrectDatabaseSetup`。
- `enable_authenticated_media: false`：该配置 v1.100 引入、**v1.120 起默认 true**，会出现"媒体上传成功但下载全 404"（原理见 `references/troubleshooting.md`）。
- `enable_registration: false`：关闭开放注册；只开注册开关而不配验证方式会报 `ConfigError`。
- `rc_*` 限速：部署初期放宽，稳定后调回默认，避免 `M_LIMIT_EXCEEDED` 影响登录/同步。

> **`server_name` 警示**：安装后不可更改（嵌入用户 ID/房间 ID/签名密钥）。改域名必须重建 DB 清空所有数据。

### 清理旧配置文件名

```bash
cd /root/matrix/synapsedata
mv localhost.log.config <你的域名>.log.config
mv localhost.signing.key <你的域名>.signing.key
```

### 常见"地雷"

| 错误 | 原因 | 修复 |
|------|------|------|
| `ConfigError` | 仅开了 `enable_registration` | 补 `enable_registration_without_verification: true` |
| `IncorrectDatabaseSetup` | Postgres 非 C locale | `database` 块加 `allow_unsafe_locale: true` |
| Permission denied | synapsedata 属主非 991 | `chown -R 991:991 ./synapsedata` |
| 媒体下载 404 | v1.120 起 `enable_authenticated_media` 默认 true | 设为 `false` 后重启 |

完整故障表（含 `M_LIMIT_EXCEEDED`、502 处理）见 `references/troubleshooting.md`。

---

## 5. 启动服务

```bash
cd /root/matrix
docker compose up -d
docker logs -f matrix-synapse 2>&1 | tail -30
docker ps --format "table {{.Names}}\t{{.Status}}"
```

---

## 6. NPM 自动配置（SSL + 反向代理）

### 前置依赖

```bash
apt install -y jq
```

### 一键配置脚本

```bash
cp <skill目录>/scripts/setup-ssl.sh /root/matrix/
chmod +x /root/matrix/setup-ssl.sh
/root/matrix/setup-ssl.sh <你的域名> <NPM管理员密码>
```

脚本依次完成：登录 NPM 取 token → 申请 Let's Encrypt 证书 → 创建到 `synapse:8008`
的反向代理（`ssl_forced` + websocket + HSTS）。任何一步失败会打印 JSON 方便定位；
证书申请失败通常是 80 端口未放行或安全组未生效。

> 与 Headscale 不同，Synapse 用 `http2_support: true` 没问题——它不依赖 HTTP/1.1 WebSocket 升级。

---

## 7. 用户管理

### 注册脚本

```bash
cp <skill目录>/scripts/register_user.sh /root/matrix/
chmod +x /root/matrix/register_user.sh
./register_user.sh <用户名> <密码>            # 普通用户
./register_user.sh <用户名> <密码> --admin    # 管理员
```

### 查询用户

```bash
docker exec matrix-db psql -U synapse -d synapse -c "\
  SELECT name,
         CASE WHEN admin=1 THEN '管理员' ELSE '普通用户' END as 角色,
         to_timestamp(creation_ts)::date as 注册日期
  FROM users ORDER BY creation_ts;"
```

### 重置密码

```bash
# 对已有用户重新执行注册命令即可重置密码
docker exec -it matrix-synapse register_new_matrix_user http://localhost:8008 \
    -c /data/homeserver.yaml -u <用户名> -p <新密码>
```

### 彻底重建数据库（清空所有数据）

```bash
cd /root/matrix
docker compose stop synapse
docker exec matrix-db psql -U synapse -d template1 -c \
  "DROP DATABASE IF EXISTS synapse;"
docker exec matrix-db psql -U synapse -d template1 -c \
  "CREATE DATABASE synapse OWNER synapse;"
docker compose start synapse
```

> ⚠ 此操作不可逆，会删除所有用户/房间/消息。

---

## 8. Federation（联邦通信）

在 NPM 对应 Proxy Host 的 Advanced Config 中追加 `.well-known/matrix/server` 与
`.well-known/matrix/client` 两个 location；完整配置、验证命令与端口说明见
`references/federation.md`。

---

## 9. TURN/STUN 服务器（音视频通话）

coturn 容器部署、`homeserver.yaml` 的 `turn_uris`/`turn_shared_secret` 配置、
媒体端口范围放行与验证方法见 `references/turn.md`。

---

## 10. 备份与恢复

### 备份脚本

```bash
cp <skill目录>/scripts/backup.sh /root/matrix/
chmod +x /root/matrix/backup.sh
/root/matrix/backup.sh   # 先手动跑一次验证
(crontab -l 2>/dev/null; echo "0 3 * * * /root/matrix/backup.sh") | crontab -
```

脚本用 `pg_dump` 导出数据库并打包 `homeserver.yaml`、签名密钥与 `.env`，保留最近 7 天。

### 恢复

```bash
cd /root/matrix
docker compose stop synapse
docker exec matrix-db psql -U synapse -d template1 -c \
  "DROP DATABASE IF EXISTS synapse;"
docker exec matrix-db psql -U synapse -d template1 -c \
  "CREATE DATABASE synapse OWNER synapse;"
gunzip -c synapse-db-<日期>.sql.gz | docker exec -i matrix-db psql -U synapse -d synapse
docker compose start synapse
```

> 必保内容：`homeserver.yaml`、`*.signing.key`、`registration_shared_secret`、`.env`。
> 签名密钥丢失会导致所有联邦服务器信任失效。

---

## 11. 安全备忘

- [ ] 关闭开放注册：`enable_registration: false` + `docker compose restart synapse`
- [ ] 修改 NPM 管理员密码
- [ ] 备份 `registration_shared_secret` 和 `*.signing.key`
- [ ] 限制端口 81 仅允许特定 IP
- [ ] 稳定后降低限速值
- [ ] 定期 `docker compose pull && docker compose up -d`
- [ ] 每月执行 `VACUUM ANALYZE`

### 客户端连接指引

```
Element 设置 → 服务器 → 自定义服务器 → https://<你的域名>
```

> Matrix 默认不支持消息的物理擦除（去中心化特性）。
> `registration_shared_secret` 泄露可被用于任意注册，务必妥善保管。

---

## 12. 参考文件索引

| 文件 | 何时读 |
|------|--------|
| `assets/docker-compose.yml` | 部署时直接复制（db + synapse + npm，版本可控） |
| `assets/.env.example` | 部署时复制为 `.env` 并填域名/密码/版本 |
| `assets/homeserver-snippets.yaml` | Synapse 配置必改片段（数据库/媒体/限速/注册） |
| `scripts/setup-ssl.sh` | NPM API 自动申请证书 + 反代（§6） |
| `scripts/register_user.sh` | 创建/重置用户（§7） |
| `scripts/backup.sh` | 定时备份（§10） |
| `references/troubleshooting.md` | 完整故障表 + 媒体 404 原理 + 限速说明 |
| `references/federation.md` | `.well-known` 联邦配置与端口 |
| `references/turn.md` | coturn 部署与音视频端口放行 |
