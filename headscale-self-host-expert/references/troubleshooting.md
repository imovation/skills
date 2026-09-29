# Headscale 故障排查

主流程见 `SKILL.md`。本文档收录完整症状-根因-修复表与诊断信息采集顺序。

## 症状速查表

| 症状 | 根因 | 修复 |
|------|------|------|
| 客户端注册成功但 11~16 秒断线反复 | Windows 会话管理断开 | 设 `UnattendedMode=always` + `--unattended`（见 SKILL.md §6） |
| 节点在线但 `tx 有值 rx=0` | 对端没连上 DERP 中继 | 检查对端 netcheck / hosts / 安全组 3478/udp |
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
| `direct connection not established` | 双方 NAT 无法打洞 | 正常，走 DERP 中继（延迟通常可接受） |
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
