# Headscale 故障排查

主流程见 `SKILL.md`。本文档收录完整症状-根因-修复表与诊断信息采集顺序。

## 症状速查表

| 症状 | 根因 | 修复 |
|------|------|------|
| 客户端注册成功但 11~16 秒断线反复 | Windows 会话管理断开 | 设 `UnattendedMode=always` + `--unattended`（见 SKILL.md §6） |
| 节点在线但 `tx 有值 rx=0` | 对端没连上 DERP 中继 | 检查对端 netcheck / hosts / 安全组 3478/udp |
| **`tailscale up` 一直卡住、服务端日志零请求**，Health 报 `failed to resolve "<域名>": no DNS fallback candidates remain` | 客户端 tailscaled 自己的 DNS 通道坏了（系统解析器却正常，极具迷惑性） | 见文末「`tailscale up` 一直卡住」小节；**实测可靠解是 hosts 固定解析** |
| `curl: Could not resolve host` + nslookup 走 `magicdns.localhost-tailscale-daemon` 超时 | DNS 死锁 | 客户端 hosts 记录；服务端 `override_local_dns: false`（见 dns-magicdns.md） |
| 客户端拿不到 IP，日志刷 `dialRegion ... context deadline exceeded` | DERP 指向官方服务器且全部超时 | 启用自建 DERP，清空 `derp.urls` |
| DERP 端点 curl 426 | 正常响应（要求升级协议） | 不是错误 |
| DERP 端点无 101 | NPM `http2_support: true` 或未开 websocket | 关 HTTP/2、开 `allow_websocket_upgrade` |
| 节点间完全不通 | 已写入的 ACL 未命中该流量（注意：空策略=全放行，不是默认拒绝） | 对照 acl.md 检查规则或临时放宽验证 |
| `initial DERPMap is empty` | 无任何 DERP 来源 | 配 `derp.urls` 或启用 `derp.server.enabled` |
| `headscale now requires a new noise.private_key_path field` | v2 协议要求 | 生成密钥并配置 `noise.private_key_path` |
| `dns.nameservers.global must be set when dns.override_local_dns is true` | 开了 DNS 覆盖但没配上游 | 补 `dns.nameservers.global` 或改 `override_local_dns: false` |
| `no IPv4 or IPv6 prefix configured` | `ip_prefixes` 列表格式已废弃 | 改为 `prefixes: {v4: ..., v6: ...}` |
| `dns.base_domain must be set when using MagicDNS` | MagicDNS 需要域名后缀 | 补 `dns.base_domain` |
| 监听地址为空 / 服务不响应 | `listen_port` 已废弃 | 改为 `listen_addr: 0.0.0.0:8080` |
| NPM `/api` 全部 502 且 backend 未监听 3000（日志停在 Fetching IP ranges） | 国内抓取 aws/cloudflare IP 段超时阻塞启动 | NPM extra_hosts 指向 127.0.0.1（npm-deploy-china.md §2.2） |
| NPM 登录 `Invalid email or password`（从未创建过账号） | 新版 NPM 不再自动建默认 admin | 设 `INITIAL_ADMIN_EMAIL/PASSWORD` 或走 Setup 向导 |
| certbot: `Server requires external account binding` | 目标 CA 要求 EAB | 先 `certbot register --eab-kid/--eab-hmac-key`（certificates.md） |
| configtest: `parsing private key: key hex string doesn't have expected type prefix privkey:` | 手写密钥文件缺前缀 | 文件内容须为 `privkey:<hex>`（generate 输出到 stdout） |
| UI 控制台 `/api/v1/policy` 报 500 | 未设置 ACL 策略时接口报错 | 写入 `{}`（=全放行，与未设置等价，acl.md §1） |
| 普通 ping 节点不通，但 `tailscale ping` 通 | 目标机 OS 防火墙拦 ICMP（正常） | 无需修复；如需 ICMP/RDP 放行见下节 |
| `tailscale ping`(disco) 通但普通数据（ICMP/TCP）不通（多见于新接入设备对仅中继节点） | 客户端数据路径未收敛（端点重协商期） | 等重协商或重启源端 Tailscale；到对端查防火墙日志确认包是否到达（见文末小节） |
| Windows RDP 连不上 | 目标机防火墙未放行 3389 | 放行 3389 且源限 100.64.0.0/10（见下节） |
| `docker pull` 超时 | Docker Hub 被墙 | daemon.json 配 registry-mirrors（npm-deploy-china.md §0） |
| `gpg: cannot open '/dev/tty'` | 非交互环境 gpg 需要 `--batch` | `gpg --batch --yes --dearmor` |
| `direct connection not established` | 双方 NAT 无法打洞 | 走 DERP 中继。**若承载 RDP 则延迟不可接受**，见下节「跨网 RDP 延迟高」 |
| 跨网 RDP 延迟极高（同一局域网的两台却很快） | 未直连、全走 DERP：TCP 套 TCP 抖动放大 | 见下节「跨网 RDP 延迟高」，根治靠 IPv6 |
| headscale-ui 刷新闪过 `alice-laptop` 等演示数据 | UI 内置 mock 数据做初始状态 | 无害，等待上游修复；真实数据随后替换 |

## DERP 中继没有生效

服务器端日志应看到自建 region 与 STUN 监听：

```bash
docker logs headscale | grep -E "derp region|derp nodes|stun server"
# 期望输出：
# derp nodes[0]: HostName:<你的域名> STUNPort:3478 DERPPort:443
# stun server started at [::]:3478
```

如果只有 region 没有 nodes，通常是 `server_url` 没配成 HTTPS 域名，或 `derp.server.enabled: false`。

客户端侧：

```powershell
tailscale debug derp-map     # 应只包含 region 999 / headscale
tailscale netcheck           # Nearest DERP: Headscale Embedded DERP
```

`netcheck` 里 `udp=false` 说明 STUN 不通，优先查云安全组与容器端口映射。

## 诊断信息采集顺序

```bash
# 服务端
docker logs headscale 2>&1 | grep -E "node connected|node disconnected|derp"
docker exec headscale headscale nodes list

# 客户端（Windows）
tailscale netcheck
tailscale status
tailscale debug derp-map
tailscale debug netmap                        # 含 PacketFilter / 各 peer Endpoints
tailscale debug peer-endpoint-changes <对端IP>  # 观察某对端端点重协商历史
Get-Content 'C:\ProgramData\Tailscale\logs\tailscaled.log' -Tail 100
```

先看服务端「节点是否在反复 connected/disconnected」，再决定查客户端还是网络链路，能少走很多弯路。

## 客户端接入类报错（tailscale up）

```text
flag provided but not defined: -unattended
→ Linux/macOS 没有该参数（Windows 专属）；Linux 用法：
  sudo tailscale up --login-server=https://<域名> --authkey=<key>

can't change --login-server without --force-reauth
→ 切换控制面必须加 --force-reauth

Access denied: checkprefs access denied
→ 需要 root；或先执行 sudo tailscale set --operator=$USER 后免 sudo

changing settings via 'tailscale up' requires mentioning all non-default flags
→ 按提示补全非默认参数，或加 --reset 重置后重来
```

## `tailscale up` 一直卡住不返回（客户端侧，Windows 高发）

**症状**：`tailscale up` 挂住无输出；加 `--timeout=Ns` 则报
`timeout waiting for Tailscale service to enter a Running state`，状态恒为
`Logged out` / `NeedsLogin`。**headscale 服务端日志里完全看不到该客户端的请求**（连 Noise 都没有）
——先据此判定是客户端问题，别在服务端反复排查。

### 第一步：拿到真正的失败原因（`status` 里没有！）

```powershell
tailscale status --json | ConvertFrom-Json | % Health     # 报错原文在这里
Get-Content C:\ProgramData\Tailscale\Logs\tailscale-service-*.txt -Tail 50   # 守护进程文件日志
```
> Windows 守护进程日志写在 `C:\ProgramData\Tailscale\Logs\`，**不在 Windows 事件日志里**
> （`Get-WinEvent -ProviderName tailscaled` 查不到，别浪费时间）。
> `tailscale debug daemon-logs` 常常什么都不输出，以上面那个文件为准。

### 第二步：区分「DNS 解析失败」还是「网络不通」

用 IP 当登录服务器试一次（绕开 DNS）：
```powershell
tailscale up --login-server=https://<服务器IP> --timeout=30s
```
- 秒回 `tls: unrecognized name`（或 x509 主机名不符）→ **TCP/TLS 正常，问题纯在 DNS 解析**
- 依旧超时 → 网络层真的不通（回本文「症状速查表」的网络类排查）

### 第三步：DNS 类失败的常见形态与对策

日志/Health 里的典型报错：
```text
fetch control key: Get "https://<域名>/key?v=NNN":
failed to resolve "<域名>": no DNS fallback candidates remain for "<域名>"
```
含义：tailscaled 解析登录域名失败，继而回退去问官方 DERP 的 bootstrap-dns（全是境外 IP，
国内网络基本超时），最终报"候选耗尽"。

**迷惑性极强**：同一台机器上 `Resolve-DnsName`、`curl https://<域名>/health`、
`tailscale debug resolve <域名>` 都正常——它们走系统解析器；只有 tailscaled 自己那条
DNS 通道（dnscache → peerapi-dns-proxy）坏了。

按性价比依次尝试（⚠️ 前三项在实测机器上**均无效**，别指望）：
1. 清 `HKLM\SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces` 下
   不属于任何现存网卡的幽灵 GUID 键（先 `reg export` 备份）；Tcpip6 同样要清
   ——参考 issue #6212，**实测无效**
2. 禁用闲置/断开的网卡 ——**实测无效**
3. 给 `Tailscale` 虚拟网卡配静态 DNS（社区常用招）——**实测无效**
4. **✅ 可靠解法：在 hosts 固定解析**
   ```powershell
   Add-Content C:\Windows\System32\drivers\etc\hosts "8.163.115.124  headscale.imovation.cn"
   Restart-Service Tailscale
   ```
   （先备份 hosts。代价：服务器换 IP 必须同步改；写进交付说明。）

### 已验证无效的"偏方"（省得再试一遍）

- 删客户端状态目录（`C:\ProgramData\Tailscale`）后重启服务
- 客户端版本升降级（1.104.1 ↔ 1.102.3 表现一致，**不是版本回归**）
- 改 Tailscale 网卡跃点、开关系统防火墙（本就全关）、清代理/PAC 环境

## ICMP 与 RDP（Windows 目标机）

- `tailscale ping` 由 tailscaled 直接应答（不进目标机协议栈），它通 ≠ 普通 ping 通；
  后者被 Windows 防火墙默认拦截属**正常现象**，不是故障。
- 放行 ICMP：`Enable-NetFirewallRule -Name FPS-ICMP4-ERQ-In`
- 放行 RDP（最小暴露，仅 tailnet 源）：

  ```powershell
  New-NetFirewallRule -DisplayName "Allow RDP from Tailscale" -Direction Inbound `
    -Protocol TCP -LocalPort 3389 -RemoteAddress 100.64.0.0/10 -Action Allow
  ```

- 排查顺序：`tailscale ping` → 目标端口可达性（`nc -zv <ip> <port>`）→ 目标机防火墙规则
  → 是否开了 ShieldsUp（`tailscale debug prefs | findstr /i shield`，true 则所有入站被丢）。

## `tailscale ping` 通但数据（ICMP/TCP）不通

典型形态：某节点（常见于**刚接入的新设备**）访问"只能走 DERP 中继"的对端失败，
但两端 `tailscale ping` 正常——disco 探测由 tailscaled 直接应答，**不代表数据面可用**。

排查顺序：

1. 两端 `tailscale ping <对端>` 确认 disco 通；`netcheck` 确认 UDP/DERP 正常。
2. **判定包是否真的到达对端**（最关键的一步）：
   - Windows 对端：开防火墙日志后读取（放行/拦截都会记录；无记录=包未到达）：

     ```powershell
     Set-NetFirewallProfile -All -LogAllowed True -LogBlocked True
     # 复现问题后：
     Select-String "<源IP>" "$env:windir\system32\LogFiles\Firewall\pfirewall.log" | Select-Object -Last 20
     ```

   - 需要更强证据时抓包：Windows Server 用 `netsh trace start capture=yes tracefile=C:\Temp\cap.etl`，
     复现后 `netsh trace stop`，再 `netsh trace convert C:\Temp\cap.etl dump=C:\Temp\cap.txt` 检索源 IP。
     ⚠️ 旧版 pktmon（仅支持 `-c/-d` 参数）没有 `--capture`，别用。
3. Windows 客户端侧查路径状态：
   - `tailscale debug netmap`：确认 `PacketFilter` 为全放行（策略 `{}` 时），并查看该对端 `Endpoints`
     （UPnP/虚拟网卡产生的不可达端点属常见噪音）。
   - `tailscale debug peer-endpoint-changes <对端IP>`：观察端点是否在持续重协商。
4. 处置：多数情况下端点重协商完成后自愈（实测约 40 分钟）；未愈则 Windows 客户端
   `Restart-Service Tailscale`；仍不通再考虑 `tailscale up --reset` 重新注册。

实测案例（2026-09）：新接入的 Windows 节点对"仅中继"节点数据不通（ICMP/TCP 全超时），disco 正常；
期间对端防火墙日志无任何记录，端点重协商自愈后立即出现 `ALLOW` 记录——两端防火墙/包过滤/ACL 均无问题。

## 跨网 RDP 延迟高（走 DERP 中继）

与上一节的区别：那里是"数据完全不通"，这里是"**能通但很卡**"。
同局域网的两台机器延迟很低，容易误判为"没问题"——那是物理交换机的功劳，与 Tailscale 无关。

### 判定

```powershell
tailscale ping --until-direct=false -c 8 <对端IP>
```

输出 `via DERP(headscale)` 即为中继。RDP 是 TCP，DERP 是 TCP(WebSocket) 隧道，
TCP 套 TCP 会把丢包重传叠加成严重卡顿。DERP 自身延迟可能只有个位数毫秒，但体感依然很差。

### 根因 1：路由器 UPnP 谎报成功

`tailscale netcheck` 显示 `PortMapping: UPnP`、日志显示 `portmap=active-U`，
**都不能证明映射真的存在**。廉价路由器（TP-Link 老固件等）会返回成功却不建规则。
用 `GetGenericPortMappingEntry` 查询会得到 `{"error_code":-40210}` 之类的空壳响应。

**唯一可靠的验证方式是外部探针**——从第三台公网机器打过来，另一端抓包：

```bash
# A 端（目标）抓包
sudo tcpdump -n -i any 'udp dst port 41641'

# B 端（任意公网可达的机器，如你自己的 VPS）发探针
python3 -c "
import socket, time
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
for i in range(5):
    s.sendto(b'X'*70, ('<目标公网IP>', 41641)); time.sleep(0.6)"
```

A 端抓到包 = 映射生效；0 包 = 没生效。

> 探针要在目标机**有 WAN 侧出向流量时**才打。NAT 映射空闲时路由器可能直接丢弃未命中流量的入向包，
> 这会让人误判成"映射没生效"。让对端保持通信（如 `tailscale ping <对端>`）再打探针。

### 根因 2：tailscale 自报端口 ≠ 手工映射端口

即使映射配好了（外部 41641 → 内部 41641），tailscale 仍会用 STUN 探测到的
**SNAT 随机端口**作为自报端点告诉对端（每次 netcheck 都变，如 `34712` / `39599` / `54224`）。
对端按这个端口来打，打的是不存在的映射，必然失败。

**tailscale 无法感知手工配置的映射，也没有配置项可以覆盖。**
所以手工端口映射对 tailscale 直连基本无效——这是本节最容易踩空的一环。

### 根因 3：双端都在 NAT 后且至少一端是硬 NAT

看对端端点（`tailscale debug netmap` 里的 `Endpoints` 或 `tailscale status --json` 的 `Addrs`）：

```
120.85.168.150:4971        ← 家庭宽带 IPv4，端口随机且频繁变化
192.168.1.223:41641        ← 另一网段的私网地址，不可达
2408:8256:d97::1:41641     ← IPv6，公网可达
```

公网端点是随机端口 + 频繁变化（家庭宽带常见），且本端没有对应映射时，打不通。
运营商 CGNAT + 对称 NAT 的组合几乎无法穿透。

### 根治：走 IPv6

**IPv6 地址天然公网可达，完全绕过 NAT 穿透**，也不受公网 IP 变动影响——
这一点与"因为公网 IP 会变才用 Tailscale"的初衷并不冲突。

两端只要都有全局 IPv6，netmap 里互相出现对方的 `[240e:...]:41641` 端点，直连立刻建立，
延迟通常降到个位数毫秒。

```bash
# 验证本机 IPv6 就绪
ip -6 addr show scope global      # 有 240e:/2408: 等全局地址
ip -6 route show | grep default  # 有 default via
curl -6 -s --noproxy '*' https://api64.ipify.org   # 出向连通
sudo tailscale status            # 看到 direct [240e:...]:41641
```

> ⚠️ **`ping -6` 不通 ≠ IPv6 不可用。** 国内运营商普遍过滤或限速 ICMPv6
> （实测电信侧 `ping -6` 100% 丢包，而 `curl -6` 完全正常）。判定一律以 `curl -6` 为准。

Windows 客户端对应验证：

```powershell
tailscale netcheck     # IPv6: yes, <地址>:端口
tailscale status       # 对端行显示 direct [240e:...]:41641
```

前置条件：路由器 WAN 口启用 IPv6，且运营商下发了前缀（电信宽带通常给 `/56` 或 `/60`）。
注意主机会同时存在三类地址：稳定地址（DHCPv6，长期不变）、mngtmpaddr（随 IA_NA 重分配）
与 RFC 4941 隐私临时地址（周期性轮换）。tailscale 把全部写入 netmap，
实测**直连走隐私地址也通畅**（抓包确认）。只要前缀稳定，就不必因地址轮换做任何干预。

### 伪方案（不要做）

| 伪方案 | 为什么无效 |
|--------|-----------|
| 给 tailscaled 加 systemd override 传 `--port=41641` | `/etc/default/tailscaled` 里 `PORT="41641"` 本就生效，tailscaled 确实监听 41641（`ss -lunp` 可验）。加 override 不改变任何行为，只是白白重启服务 |
| 信任 `netcheck` 的 `PortMapping: UPnP` | 见根因 1，路由器可能谎报成功 |
| 把 `41641` 映射到 tailscaled 以外的其他端口 | tailscale 自报的是随机 SNAT 端口，映射对不上（见根因 2） |
| 反复重启 tailscale / `--reset` 重注册 | 端点是 NAT 行为，重启客户端改变不了对端打不通的事实 |

### 实测案例（2026-10）

拓扑：hasee（公司，Linux，100.64.0.1）↔ surface（家，Windows，100.64.0.4）经 Tailscale 远程桌面。
同公司另一台 shining（100.64.0.2）与 hasee 同局域网，延迟 8ms，**因此最初误以为整体网络正常**。

过程：

1. `tailscale ping` 显示 `via DERP(headscale)`，延迟 11~28ms 且偶发 117ms → 判定中继。
2. 外部探针测试发现 `41641/udp` 入站 0 包到达，路由器只有 TCP 22 的映射 → 根因 1。
3. 手工配置 `UDP 41641 → 192.168.1.200:41641` 后外部探针可达（收到 7 个包）→ 映射确实生效了。
4. 但直连**依然失败**：hasee 自报 `113.66.x.x:34712`，与映射的 41641 不一致 → 根因 2。
5. 进一步发现 surface 侧公网端点是家庭宽带随机端口（`120.85.x.x:4971`），
   而 surface 自己有原生 IPv6（`2408:8256:d97::/64`），hasee 没有 → 根因 3。
6. **在公司路由器开启 IPv6** → hasee 获得 `240e:3b5:cf2:6492::/64`，
   两端 netmap 出现对方 IPv6 端点 → 直连建立，**RTT 8~14ms**。

过程中还观察到办公网公网 IP 在数天内从 `113.68.254.176` → `113.66.228.28` → `113.68.255.86`
多次变更——这正是该场景必须用 Tailscale 而非公网端口直连 RDP 的原因，
也再次说明「动态 IP 不影响配端口映射、但会让手工直连失效」。

**教训**：先确认两端在同一局域网时是否也慢（若不慢，说明问题专属于跨网路径），
再按根因 1→2→3 逐层排查；不要在"局域网正常"的表象上停手。
能用 IPv6 就别在 NAT 穿透上纠缠。
