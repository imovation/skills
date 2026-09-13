# NPM 全新部署（国内环境）

当目标服务器**还没有** NPM 时需要从零部署。本文档含完整 compose 模板（`assets/npm-compose.yml`）、
首次启动的三个高频坑与安全加固。若已有 NPM 在跑，直接复用（见 `npm-reverse-proxy.md`）。

## 0. 前置：安装 Docker（国内）

```bash
# apt 源用阿里云 docker-ce 镜像（download.docker.com 在国内不可达）
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg \
  | gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg   # 非 tty 必须 --batch --yes
CODENAME=$(. /etc/os-release && echo "$VERSION_CODENAME")
printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.aliyun.com/docker-ce/linux/ubuntu %s stable\n' \
  "$(dpkg --print-architecture)" "$CODENAME" > /etc/apt/sources.list.d/docker.list
apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin
```

Docker Hub 拉取超时则配置加速器（`/etc/docker/daemon.json`，重启 docker）：

```json
{ "registry-mirrors": [
    "https://docker.1ms.run",
    "https://docker.m.daocloud.io",
    "https://docker.xuanyuan.me",
    "https://dockerproxy.net"
] }
```

## 1. 部署模板

复制 `assets/npm-compose.yml` 到 `/opt/npm/docker-compose.yml`，然后：

```bash
mkdir -p /opt/npm/{data,letsencrypt}
docker network create headscale_default   # headscale 与 NPM 共用网络，可容器名互访
cd /opt/npm && docker compose up -d
```

模板要点（每项都有坑的原因）：

- `extra_hosts` 把 aws/cloudflare 的 ip-ranges 域名指向 127.0.0.1：**否则 backend 启动卡死**
  （见 §2.2）
- `INITIAL_ADMIN_EMAIL/PASSWORD`：**新版 NPM 不再自动创建默认账号**（见 §2.1）
- `LE_SERVER`：签发走 ZeroSSL（见 `certificates.md`）

## 2. 首次启动三大坑

### 2.1 登录提示 "Invalid email or password" 但从未设置过账号

新版 NPM（2.12+）不再创建 `admin@example.com / changeme`，两种解法：

1. **环境变量预置（推荐，可自动化）**：compose 加 `INITIAL_ADMIN_EMAIL` / `INITIAL_ADMIN_PASSWORD`，
   重启后日志出现 `Creating a new user ... Initial admin setup completed`
2. 浏览器打开面板走首次 Setup 向导（无头服务器不方便）

### 2.2 /api 全 502，backend 不监听 3000（日志停在 "Fetching IP ranges"）

NPM 启动时抓取 `ip-ranges.amazonaws.com` / `www.cloudflare.com` 等，国内域名超时导致初始化卡住。
症状：`/login` 200 但 `/api/tokens` 502；`docker exec npm cat /proc/net/tcp` 没有 3000 监听。

解法（模板已含）：extra_hosts 指向 127.0.0.1，抓取**立即失败**且不阻塞：

```yaml
extra_hosts:
  - "ip-ranges.amazonaws.com:127.0.0.1"
  - "www.cloudflare.com:127.0.0.1"
  - "ip-ranges.atlassian.com:127.0.0.1"
  - "api.github.com:127.0.0.1"
```

正常启动的标志（docker logs npm）：`Backend PID <n> listening on port 3000 ...`

### 2.3 证书签发链路

NPM 只内置 letsencrypt provider；国内 LE 不可达时按 `certificates.md`：设 `LE_SERVER` +
`certbot register` 预注册 EAB 账户。**注意容器重建后 certbot 账户仍在**（挂载在 ./letsencrypt）。

## 3. 安全加固

- **81 面板端口**：默认映射到公网即高危。二选一：
  - 云安全组**不放行 81**（推荐；本次部署即如此）——面板仅本机可达，用 SSH 隧道访问：
    ```bash
    ssh -L 8181:127.0.0.1:81 root@<服务器>
    # 浏览器访问 http://127.0.0.1:8181
    ```
  - 安全组把 81 限制为固定来源 IP
- 管理密码修改 API（无需进 UI）：
  ```bash
  curl -X PUT http://127.0.0.1:81/api/users/me/auth \
    -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
    -d '{"type":"password","current":"<旧>","secret":"<新>"}'
  ```
- 后台逻辑：容器端口绑定 + 安全组双层；不要只依赖 NPM 自身认证

## 4. 与 headscale 联动

- 两容器需在同一 docker network（模板已声明 `headscale_default` external），
  NPM 反代可用 `http://headscale:8080`
- 反代详细配置（websocket、http2 关闭、/hsui/ 子路径）见 `npm-reverse-proxy.md`
