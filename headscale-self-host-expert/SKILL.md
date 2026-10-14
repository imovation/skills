---
name: headscale-self-host-expert
description: 专门用于在 Linux 服务器上部署和维护 Headscale（自建 Tailscale 控制服务器）。当用户需要搭建 Headscale、接入 Tailscale 客户端、配置自建 DERP 中继、Nginx Proxy Manager 反代、MagicDNS、ACL 策略，或遇到 "NoState" / "could not connect to ... DERP relay server" / "initial DERPMap is empty" / "no IPv4 or IPv6 prefix configured" / "noise.private_key_path" / DNS 解析死锁 / 节点 relay tx 有值但 rx=0 等错误时，务必使用此 Skill。涵盖 Docker 编排、Windows 客户端无人值守修复、Web 控制台部署等完整工作流，尤其适配中国大陆网络环境。
---

# Headscale 自建专家 (Headscale Self-Host Expert)

在 Ubuntu/Debian 服务器上构建生产级 Headscale（Tailscale 控制面替代）环境，专为国内网络环境优化。

本文件是主流程；部署模板在 `assets/`，可执行脚本在 `scripts/`，排障与专项配置在 `references/`，需要时再读。

## 0. 前置准备

### 系统要求
| 规格 | 建议 |
|------|------|
| CPU | 1 核起（Headscale 极轻量） |
| 内存 | 1G 起（512M 也可运行，注意预留余量） |
| 磁盘 | 10G 起（SQLite 数据极小） |
| OS | Ubuntu 24.04 / 22.04 |

### 域名与 DNS
```bash
# 获取服务器公网 IP（阿里云等 NAT 环境）
curl -s https://api.ipify.org

# 确认域名已解析到该 IP
dig +short <你的域名>
```

> **必须使用 HTTPS 域名接入客户端**。Tailscale 客户端默认拒绝明文 HTTP 控制面。
> 已有服务器跑着 Nginx Proxy Manager (NPM) 时直接复用，不要重复部署反代；
> **没有 NPM 时**按 `references/npm-deploy-china.md` 从零部署（模板与国内三坑已备）。
> 证书签发策略（国内 LE 被墙、ZeroSSL 免网页 EAB）见 `references/certificates.md`。

### 端口全景
| 端口 | 用途 | 云安全组 | 说明 |
|------|------|---------|------|
| 443 | HTTPS 控制面 + DERP 中继 + Web UI | ✅ 放行 | NPM 统一入口，DERP 靠 WebSocket 升级 |
| 3478/udp | STUN（NAT 探测） | ✅ 放行 | 自建 DERP 必需，不放过 netcheck 会异常 |
| 8080 | Headscale 内部 HTTP | ❌ 不放行 | NPM 通过 Docker 内网访问即可 |
| 81 | NPM 管理面板 | ❌ 不放行 | 仅 SSH 隧道访问（`ssh -L 8181:127.0.0.1:81`）；管理员初始化见 npm-deploy-china.md |

---

## 1. 快速部署

### 1.1 准备目录与模板

```bash
mkdir -p /opt/headscale/{config,data}
# 从本 Skill 的 assets/ 复制模板（<skill目录> 即本 SKILL.md 所在目录）
cp <skill目录>/assets/docker-compose.yml /opt/headscale/docker-compose.yml
cp <skill目录>/assets/config.yaml       /opt/headscale/config/config.yaml
```

把两个文件里的 `<你的域名>` 替换为真实域名后使用。模板中几处关键设计（含原因）：

- **镜像固定 `v0.29.3`**：Headscale 历史上多次出现破坏性配置变更（v0.23/v0.29），
  用 `latest` 时一次 `docker compose pull` 就可能让服务起不来。升级流程见 §7。
- `127.0.0.1:8080:8080`：只绑本机，NPM 通过 Docker 内网访问，不暴露公网。
- `3478:3478/udp`：自建 DERP 的 STUN 端口，必须映射且安全组放行。
- `headscale_default` 网络声明为 `external`：若不存在，先 `docker network create headscale_default`，
  或删掉 compose 里的 `external` 让 compose 自建。
- `headscale-ui` 为可选 Web 控制台，不用可整段删除；部署细节见 `references/npm-reverse-proxy.md`。

### 1.2 生成密钥（启动前必做）

镜像的 ENTRYPOINT 就是 headscale 二进制，命令**不要再重复写 headscale**：

```bash
HS_VERSION=v0.29.3   # 与 docker-compose.yml 中的镜像 tag 保持一致

# noise 私钥（Tailscale v2 协议必需）
docker run --rm -v /opt/headscale/data:/var/lib/headscale \
  headscale/headscale:$HS_VERSION generate private-key \
  --output /var/lib/headscale/noise_private.key

# 嵌入式 DERP 私钥（启用自建中继时必需）
docker run --rm -v /opt/headscale/data:/var/lib/headscale \
  headscale/headscale:$HS_VERSION generate private-key \
  --output /var/lib/headscale/derp_server_private.key
```

> 错误写法：`docker run ... headscale/headscale:$HS_VERSION headscale generate ...`
> 会报 `unknown command "headscale" for "headscale"`。
>
> 实测补充：部分镜像版本的 `generate private-key --output <path>` 只把密钥打印到 stdout（`privkey:<hex>`）
> 而不落盘。若 `configtest` 报 `parsing private key: key hex string doesn't have expected type prefix privkey:`，
> 即手写密钥文件缺前缀——文件内容应为 `privkey:<hex>`，权限 600。

### 1.3 配置验证与启动

```bash
# 先验证配置（推荐，比反复重启快）
docker run --rm -v /opt/headscale/config:/etc/headscale \
  -v /opt/headscale/data:/var/lib/headscale \
  headscale/headscale:$HS_VERSION configtest

cd /opt/headscale && docker compose up -d
docker logs headscale 2>&1 | tail -20
```

### 1.4 规划跨网连通性（部署时就要定）

Headscale 本身只是控制面，**数据面走不通不会影响接入**，但会在后续使用中表现为
「远程桌面/跨网访问很卡」。这个决定要在接入客户端**之前**做完。

| 场景 | 推荐 | 说明 |
|------|------|------|
| 客户端之间同局域网 | 直连（LAN） | 物理交换机直连，延迟最低，不需要任何配置 |
| 跨网、且公网 IP 固定 | 手工端口映射 + 固定 tailscale 端口 | tailscale 自报端口与映射对不上时仍会失败，见 §4 陷阱 |
| **跨网、公网 IP 动态**（国内家庭/办公宽带常态） | **优先让两端都支持 IPv6** | 绕过 NAT 穿透，且不受 IP 变动影响 |
| 两端都只有 IPv4 且在硬 NAT 后 | 只能走 DERP 中继 | 降低 RDP 画质/关视频重定向等作为缓解 |

**IPv6 是首选**：地址天然公网可达，不需要任何端口映射或 UPnP。
国内运营商普遍已给 IPv6 前缀（电信给 `/56` 或 `/60`），在路由器 WAN 口启用即可。

> 判定本机 IPv6 是否真的可用，**不要用 `ping -6`**——国内运营商普遍过滤/限速 ICMPv6
> （实测 100% 丢包）。用 `curl -6 -s https://api64.ipify.org` 判断。
> 通常会同时存在三类地址：路由器分配的稳定地址（DHCPv6，长期不变）、
> mngtmpaddr（依赖 IA_NA，前缀重分配时变）、RFC 4941 隐私临时地址（按标准周期性轮换）。
> tailscale 会把全部可用地址写入 netmap，实测**用隐私地址直连也通畅**，无需人工干预；
> 只要前缀稳定就不必操心地址轮换。

---

## 2. 常见配置报错（v0.23 → v0.29 变迁）

完整配置模板见 `assets/config.yaml`。以下是升级/迁移时最高频的报错：

| 报错信息 | 原因 | 修复 |
|---------|------|------|
| `headscale now requires a new noise.private_key_path field` | v2 协议要求 | 生成密钥并配置 `noise.private_key_path` |
| `dns.nameservers.global must be set when dns.override_local_dns is true` | 开了 DNS 覆盖但没配上游 | 补 `dns.nameservers.global` 或改 `override_local_dns: false` |
| `no IPv4 or IPv6 prefix configured` | `ip_prefixes` 列表格式已废弃 | 改为 `prefixes: {v4: ..., v6: ...}` |
| `dns.base_domain must be set when using MagicDNS` | MagicDNS 需要域名后缀 | 补 `dns.base_domain` |
| `initial DERPMap is empty` | 没有任何 DERP 来源 | 配 `derp.urls` 或启用 `derp.server.enabled` |
| 监听地址为空 / 服务不响应 | `listen_port` 已废弃 | 改为 `listen_addr: 0.0.0.0:8080` |

---

## 3. NPM 反向代理（HTTPS 关键配置）

### 3.1 网络互通

> 服务器**没有 NPM** 时先按 `references/npm-deploy-china.md` 从零部署（含默认管理员、
> IP ranges 卡死等国内坑与 `assets/npm-compose.yml` 模板）；证书签发链路见 `references/certificates.md`。

让 NPM 容器加入 headscale 网络，之后可用容器名直连：

```bash
docker network connect headscale_default <npm容器名>
```

### 3.2 两个致命细节

通过 NPM API 或面板创建代理时：

1. `http2_support: false` —— DERP 依赖 HTTP/1.1 WebSocket 升级，开 HTTP/2 会导致客户端永远连不上中继（健康检查报 "could not connect to ... DERP relay server"）。
2. `allow_websocket_upgrade: true` —— 不开无法升级协议。

其余字段：`forward_scheme: http`、`forward_host: headscale`、`forward_port: 8080`、`ssl_forced: true`、`trust_forwarded_proto: true`。
完整的 API 调用（取 token、创建/更新 proxy-host）见 `references/npm-reverse-proxy.md`。

### 3.3 验证链路

```bash
curl -s https://<你的域名>/health        # {"status":"pass"}

# DERP 端点：普通请求返回 426（正常），带升级头返回 101
curl -sk -o /dev/null -w "%{http_code}\n" https://<你的域名>/derp
curl -sk -o /dev/null -w "%{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: derp" https://<你的域名>/derp
```

> **两个局限，勿过度解读：**
> 1. 若浏览器弹证书警告而手动继续访问，JSON 仍会返回——它只证明 HTTPS 可访问，不代表证书受信。
> 2. **`/health` 通过 ≠ 客户端能接入**。它只是普通 HTTP 接口，不验证 WebSocket 升级（DERP 依赖）与控制协议。常见故障（如 NPM 开着 HTTP/2 导致 DERP 连不上）时 `/health` 依然是 200。
>    必须配合上面的 `/derp` 426/101 测试与客户端的 `tailscale netcheck` 才能确认可接入。

---

## 4. 自建 DERP 中继（国内网络必备）

### 为什么必须自建

官方 DERP 服务器（`controlplane.tailscale.com/derpmap/default`）在国内几乎全部超时：

```
netcheck: report: udp=false derp=0
health: Tailscale could not connect to the 'Bengaluru' relay server
```

即使控制面能连上，节点之间也无法建立中继通信（表现为 `tx > 0, rx = 0`）。

### 服务器端确认

```bash
docker logs headscale | grep -E "derp region|derp nodes|stun server"
# 应看到：
# derp nodes[0]: HostName:<你的域名> STUNPort:3478 DERPPort:443
# stun server started at [::]:3478
```

### 云安全组放行

- TCP 443（DERP over HTTPS，已有）
- **UDP 3478（STUN，最容易漏）**

### 客户端确认

```powershell
tailscale debug derp-map     # 应只包含 region 999 / headscale
tailscale netcheck           # Nearest DERP: Headscale Embedded DERP
```

---

## 5. 用户与密钥管理（CLI）

```bash
# 创建用户
docker exec headscale headscale users create <用户名>

# 查看用户（注意 ID，preauthkey 用 ID 不用名字）
docker exec headscale headscale users list

# 创建接入密钥（--user 只接受数字 ID！）
docker exec headscale headscale preauthkeys create --user 1 --reusable --expiration 24h

# 创建 API Key（Web UI / REST API 用，有效期按需）
docker exec headscale headscale apikeys create --expiration 720h

# 查看节点
docker exec headscale headscale nodes list
```

> 常见错误：`--user alice` → `strconv.ParseUint: parsing "alice": invalid syntax`，必须传 ID。

---

## 6. 客户端接入

### 通用命令

```bash
# Linux / macOS（没有 --unattended，那是 Windows 专属参数）
sudo tailscale up --login-server=https://<你的域名> --authkey=<preauthkey>
# 切换过 login-server 时须加 --force-reauth
# Linux 免 sudo 管理：sudo tailscale set --operator=$USER

# Windows（推荐配合无人值守模式，见下节）
tailscale up --login-server=https://<你的域名> --authkey=<preauthkey> --unattended
```

接入成功的标志（服务器端）：

```bash
docker exec headscale headscale nodes list   # 节点 online + 已分配 100.64.0.x
```

### Windows 客户端 NoState 修复（重点）

症状：

```
tailscale status
# Health check: Tailscale is starting. Please wait.
unexpected state: NoState
tailscale ip
# no current Tailscale IPs; state: NoState
```

服务端日志却显示节点连接 11~16 秒后反复断开。根因是 Windows 会话管理（RDP/控制台切换）主动断开 Tailscale。修复：

```powershell
# 1. 停止服务
Stop-Service Tailscale -Force

# 2. 设置无人值守模式（核心）
Set-ItemProperty -Path "HKLM:\SOFTWARE\Tailscale IPN" -Name "UnattendedMode" -Value "always" -Type String

# 3. 启动服务
Start-Service Tailscale

# 4. 接入（设置 UnattendedMode 后必须显式带上 --unattended）
tailscale up --login-server=https://<你的域名> --authkey=<key> --unattended

# 5. 等待 15 秒后验证
tailscale status
tailscale ip
```

> 若报 `changing settings via 'tailscale up' requires mentioning all non-default flags`，
> 按提示补全 flags 或用 `--reset` 重置后重来。

### Windows 远程桌面（RDP）接入

目标机放行 3389（最小暴露，仅 tailnet 源），之后 `mstsc /v:<100.64.x.x>` 即可：

```powershell
New-NetFirewallRule -DisplayName "Allow RDP from Tailscale" -Direction Inbound `
  -Protocol TCP -LocalPort 3389 -RemoteAddress 100.64.0.0/10 -Action Allow
```

> 普通 ICMP ping 不通**不等于**故障：Windows 防火墙默认拦截，而 `tailscale ping` 由 tailscaled
> 直接应答（不进系统协议栈）。排查顺序与放行命令见 `references/troubleshooting.md`「ICMP 与 RDP」。

### 验证命令速查

| 命令 | 用途 |
|------|------|
| `tailscale ip` | 确认拿到 100.64.0.x |
| `tailscale netcheck` | 确认 UDP / Nearest DERP |
| `tailscale ping <对端IP>` | 验证节点互通（比 ICMP ping 准确） |
| `tailscale debug derp-map` | 确认 DERP 地图只含自建 region |
| `tailscale debug netmap` | 看各 peer 的 `Endpoints`——判断能否直连的关键（见 §4 陷阱） |
| `tailscale ping` 输出 `direct connection not established` | 仅传输小文件时可接受；**承载 RDP 时不可接受**，见 §4 |
| `curl -6 -s https://api64.ipify.org` | 判定 IPv6 出向是否可用（**不要用 `ping -6`**，国内普遍过滤 ICMPv6） |

---

## 7. 故障排查与维护

### 7.1 高频症状速查

| 症状 | 根因 | 修复 |
|------|------|------|
| 客户端注册成功但 11~16 秒断线反复 | Windows 会话管理断开 | 按 §6 NoState 修复 |
| 节点在线但 `tx 有值 rx=0` | 对端没连上 DERP 中继 | 检查对端 netcheck / 安全组 3478/udp |
| 节点间完全不通 | ACL 未命中（注意空策略=全放行） | 见 `references/acl.md` |
| `tailscale ping` 通但普通 ping 不通 | 目标机系统防火墙拦 ICMP（正常） | 无需修复；RDP/ICMP 放行见 troubleshooting |
| `tailscale ping` 通但数据（ICMP/TCP）不通（个别节点，尤其新接入对仅中继对端） | 客户端数据路径未收敛 | 等端点重协商或重启源端；见 troubleshooting「disco 通但数据不通」 |
| UI/API `/api/v1/policy` 报 500 | 未设置 ACL 策略 | 写入 `{}`（=全放行；`{"grants":[]}` 才是拒绝一切） |
| NPM `/api` 全 502（backend 未就绪） | IP ranges 抓取卡死 | 见 `references/npm-deploy-china.md` §2.2 |
| `initial DERPMap is empty` | 无任何 DERP 来源 | 启用 §4 自建 DERP |
| DNS 解析超时 / 死锁 | `override_local_dns` 接管系统 DNS | 见 `references/dns-magicdns.md` |
| 跨网远程桌面延迟极高（局域网的两台却很快） | 未直连，全走 DERP：TCP 套 TCP | 优先开 IPv6（§1.4）；排查全过程见 `references/troubleshooting.md` §跨网 RDP 延迟高 |

完整故障表、DERP 链路细节与诊断采集顺序见 `references/troubleshooting.md`。

### 7.1.1 三个必须记住的陷阱

这些坑在 `references/troubleshooting.md` 有完整展开，此处只列结论：

1. **路由器的 UPnP 会谎报成功。** `netcheck` 显示 `PortMapping: UPnP`、日志显示
   `portmap=active-U`，都不能证明映射真的存在（廉价路由器常见）。
   唯一可靠的验证是**外部探针 + 抓包**。

2. **tailscale 自报端口 ≠ 手工映射端口。** 即使手工配了 `外部41641 → 内部41641`，
   tailscale 仍用 STUN 探测到的 **SNAT 随机端口**（每次都变）告诉对端，对端按此来打必然失败。
   tailscale 无法感知手工映射，也没有配置项可覆盖。**所以手工端口映射对 tailscale 直连基本无效。**

3. **`--port=41641` 的 systemd override 是伪方案。** `/etc/default/tailscaled` 里
   `PORT="41641"` 本就生效，tailscaled 确实监听 41641。加 override 不改变任何行为，
   只是白白重启一次服务（`ss -lunp` 可先验证实际监听端口）。

**结论：跨网连通性优先上 IPv6，不要在 NAT 穿透上纠缠。**

### 7.2 备份（SQLite 在线安全备份，已实测）

`scripts/backup.sh` 无需停服，`.backup` 会自动合并 WAL：

```bash
cp <skill目录>/scripts/backup.sh /opt/headscale/backup.sh
chmod +x /opt/headscale/backup.sh
/opt/headscale/backup.sh          # 先手动跑一次验证
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/headscale/backup.sh >> /var/log/headscale-backup.log 2>&1") | crontab -
```

恢复：

```bash
cd /opt/headscale
docker compose stop headscale
tar xzf /opt/headscale-backup/headscale-<DATE>.tar.gz -C /opt
cp /opt/headscale-backup/db-<DATE>.sqlite /opt/headscale/data/db.sqlite
rm -f /opt/headscale/data/db.sqlite-shm /opt/headscale/data/db.sqlite-wal
docker compose start headscale
```

> 必保内容：`config.yaml`、`noise_private.key`、`derp_server_private.key`、`db.sqlite`。
> `noise_private.key` 丢失会导致所有客户端重新注册；`db.sqlite` 丢失则节点/用户/密钥全没。
> 备份目录权限 700、文件 600（含私钥）。

### 7.3 升级（固定版本流程）

```bash
# 1. 先备份
/opt/headscale/backup.sh

# 2. 对照目标版本的 config-example.yaml 检查字段变更
#    https://raw.githubusercontent.com/juanfont/headscale/<新版本tag>/config-example.yaml

# 3. 修改 /opt/headscale/docker-compose.yml 中的镜像 tag，例如 v0.29.3 → v0.30.0

# 4. 拉取并重建
cd /opt/headscale
docker compose pull
docker compose up -d
docker logs headscale 2>&1 | tail -10

# 5. 回归验证
curl -sk https://<你的域名>/health
docker exec headscale headscale nodes list
```

> Headscale 多个大版本发生过破坏性配置字段调整（v0.23/v0.29），
> 因此**永远固定 tag、升级前必看示例配置、必先备份**，不要用 `latest`。

### 7.4 安全清单

- [ ] `server_url` 使用 HTTPS，证书自动续期正常（国内优先 ZeroSSL，见 `references/certificates.md`）
- [ ] NPM 管理端口 81 不暴露公网（安全组不放行 + SSH 隧道，见 `references/npm-deploy-china.md` §3）
- [ ] 容器端口绑定收紧（模板已做：`127.0.0.1:8080:8080`，NPM 走 Docker 内网）
- [ ] API Key 设置有限有效期并定期轮换
- [ ] 定期备份 `noise_private.key` + `db.sqlite`（见 §7.2）
- [ ] ACL 按最小权限原则收紧（不要长期全放行，方法见 `references/acl.md`；
      注意 `{}`=全放行、`{"grants":[]}`=拒绝一切，收紧时先给自己留兜底规则）
- [ ] 客户端使用 `--unattended`（Windows）+ preauthkey 接入，避免依赖 GUI 会话

### 7.5 数据面连通性清单（接入后必须实测）

控制面接通 ≠ 数据面可用。以下逐项确认，任一项不过关就先别交付：

- [ ] `tailscale ping <对端>` 两端都跑过；承载 RDP 时**必须是 `direct`**，不能是 `via DERP`
- [ ] `tailscale status` 里对端行显示 `direct <IP>:端口` 或 `direct [IPv6]:41641`
- [ ] 若依赖 IPv6：`ip -6 addr show scope global` 有全局地址、`ip -6 route show` 有 `default via`、
      `curl -6 -s https://api64.ipify.org` 出向通（**不用 `ping -6` 判断**，见 §1.4）
- [ ] 若依赖端口映射：用**外部探针**实测（路由器 UPnP 可能谎报成功，见 §4）
- [ ] 跨网 RDP 实际登录一次确认手感，同局域网的两台延迟低**不能**作为跨网正常的依据

> 只跑 `tailscale netcheck` 看「节点都 online」是不够的——它在全中继的情况下也会一切正常。

---

## 8. 参考文件索引

| 文件 | 何时读 |
|------|--------|
| `assets/docker-compose.yml` | 部署时直接复制（固定版本 headscale + 可选 headscale-ui） |
| `assets/config.yaml` | 部署时直接复制（v0.29 完整可用模板，含注释） |
| `assets/npm-compose.yml` | 服务器没有 NPM 时从零部署（国内坑已内置） |
| `scripts/backup.sh` | 配置定时备份（§7.2） |
| `references/troubleshooting.md` | 完整故障表 + 诊断采集顺序 + DERP 链路细节 + **跨网 RDP 延迟高（IPv6 根治 + UPnP 谎报坑）** |
| SKILL.md §1.4 / §7.1.1 / §7.5 | 部署期连通性规划 / 三个必记陷阱 / 数据面实测清单 |
| `references/certificates.md` | 证书策略：LE 被墙、ZeroSSL 免网页 EAB、NPM 集成续期 |
| `references/npm-deploy-china.md` | NPM 全新部署：默认管理员、IP ranges 卡死、81 加固 |
| `references/dns-magicdns.md` | DNS 死锁 / MagicDNS 配置 |
| `references/acl.md` | ACL/grants 策略语法与最小权限示例 |
| `references/npm-reverse-proxy.md` | NPM API 完整调用、headscale-ui 子路径 |
