# MagicDNS 与 DNS 死锁

## 死锁链条

1. `override_local_dns: true` 把客户端系统 DNS 全部指向 MagicDNS（`100.100.100.100`）
2. MagicDNS 需要 Tailscale 数据通道（DERP）才能向上游转发解析
3. DERP 又需要先解析控制面域名 `<你的域名>` 才能连接
4. 一旦 DERP 断开 + 客户端原有 DNS 通路被接管 → **永远解析不了，死锁**

这也是为什么模板默认用 `override_local_dns: false`。

## 正确配置

```yaml
dns:
  base_domain: tailnet.<你的域名>   # 用自己的域，不要 example.com
  override_local_dns: false        # 关键：拆分 DNS
```

- `false` = 只有 `*.tailnet.<你的域名>` 走 MagicDNS，其余访问走本地/公司 DNS
- 公司内网 DNS 不受影响，也避免死锁

## 客户端应急修复（已死锁时）

```powershell
# hosts 记录优先于 DNS 查询，直接打断死锁
Add-Content -Path "$env:SystemRoot\System32\drivers\etc\hosts" `
  -Value "<服务器公网IP> <你的域名>"
Restart-Service Tailscale
```

> 验证时**不要用 nslookup**（绕过 hosts），用 `ping <域名>` 或 `Resolve-DnsName`。

## 验证 MagicDNS

```powershell
Resolve-DnsName <设备名>.tailnet.<你的域名>   # 应返回 100.64.0.x
Get-DnsClientServerAddress -AddressFamily IPv4   # 本地 DNS 应恢复为公司/本地 DNS
```
