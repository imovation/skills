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
Get-Content 'C:\ProgramData\Tailscale\logs\tailscaled.log' -Tail 100
```

先看服务端「节点是否在反复 connected/disconnected」，再决定查客户端还是网络链路，能少走很多弯路。
