# NPM 反向代理与 Web 控制台

本文档是 SKILL.md §3 / §6 的展开：完整 NPM API 配置、headscale-ui 部署、NPM 管理端口加固。

## 1. 通过 NPM API 配置代理

```bash
# 登录获取 token
TOKEN=$(curl -s -X POST http://127.0.0.1:81/api/tokens \
  -H "Content-Type: application/json" \
  -d '{"identity":"<NPM管理员邮箱>","secret":"<NPM密码>"}' | jq -r .token)
```

新建代理（或 `PUT /api/nginx/proxy-hosts/<id>` 复用已有记录）：

```bash
curl -s -X POST http://127.0.0.1:81/api/nginx/proxy-hosts \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "domain_names": ["<你的域名>"],
    "forward_scheme": "http",
    "forward_host": "headscale",
    "forward_port": 8080,
    "allow_websocket_upgrade": true,
    "http2_support": false,
    "block_exploits": true,
    "caching_enabled": false,
    "ssl_forced": true,
    "trust_forwarded_proto": true,
    "certificate_id": <证书ID>,
    "meta": {"letsencrypt_agree": false, "dns_challenge": false}
  }'
```

> **两个致命细节：**
> 1. `http2_support: false` —— DERP 依赖 HTTP/1.1 WebSocket 升级，开 HTTP/2 会导致客户端永远连不上中继（健康检查报 "could not connect to ... DERP relay server"）。
> 2. `allow_websocket_upgrade: true` —— 不开无法升级协议。

## 2. Web 控制台（headscale-ui）

部署见 `assets/docker-compose.yml`。镜像选型结论：

| 项目 | 结论 |
|------|------|
| `MunMunMiao/headscale-ui` | ✅ 推荐，活跃维护，REST API 兼容 v0.29 |
| `goodieshq/headscale-admin` | ⚠️ 发布版本对应旧版 headscale，API 有漂移风险 |

### NPM 子路径配置

在代理主机的 Advanced Config 中追加（`proxy_pass` **不要**带尾部斜杠）：

```nginx
location = /hsui { return 308 /hsui/; }
location /hsui/ {
    proxy_pass http://headscale-ui:80;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

### 使用

1. 访问 `https://<你的域名>/hsui/`
2. 连接配置：**Mode 选 Real**，Server URL 填 `https://<你的域名>`（不带 `/api/v1`），填入 `apikeys create` 生成的 key
3. **「Policy/ACL」页面在导航里叫「访问控制 / Access controls」**（第 6 个标签），不是直接叫 Policy

## 3. NPM 管理端口 81 加固（二选一）

### 方案 A：云安全组限制来源 IP（推荐）

阿里云控制台 → ECS → 安全组 → 入方向规则：

- 把 81 端口规则的源从 `0.0.0.0/0` 改为你的固定公网 IP（如 `1.2.3.4/32`）
- 或直接删除 81 规则（完全关闭公网访问）

```bash
# 在需要访问 NPM 的电脑上查当前公网 IP
curl -s https://api.ipify.org
```

### 方案 B：SSH 隧道（不开任何端口，最安全）

```bash
# 在本地电脑执行，保持 SSH 连接
ssh -L 8181:127.0.0.1:81 root@<服务器IP>
# 然后浏览器访问 http://127.0.0.1:8181 管理 NPM
```

> 原理：`ssh -L` 把本地 8181 转发到服务器的 `127.0.0.1:81`（docker-proxy 监听 0.0.0.0:81，
> 本机回环同样可达）。因此安全组里 81 可以不放开，NPM 管理面完全不暴露公网。
