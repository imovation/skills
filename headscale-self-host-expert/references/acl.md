# ACL 策略

> **默认行为（v0.29.3 官方文档确认）：不配置任何策略 = 允许全部互通。**
> 想要"拒绝一切"必须显式设置 `{"grants": []}`；策略中省略 `grants`/`acls` 段同样视为允许全部。
> 这一点与直觉相反——排查节点互通问题时，不要一上来就怀疑 ACL 拦截。

> **语法选择**：v0.29 同时支持旧版 `acls` 与新推荐语法 `grants`。官方推荐 `grants`
> （`acls` 属遗留语法，不再新增功能），以下示例均用 `grants`。

## 1. 允许全部（最简默认）

```bash
curl -sk -X PUT https://<你的域名>/api/v1/policy \
  -H "Authorization: Bearer <API Key>" \
  -H "Content-Type: application/json" \
  -d '{"policy":"{}"}'
```

## 2. 收紧示例（最小权限）

先规划再动手，例如"自己的设备全互通，外来设备只能访问特定端口"：

```json
{
  "grants": [
    {
      "src": ["imovation@"],
      "dst": ["imovation@"],
      "ip": ["*"]
    },
    {
      "src": ["tag:shining"],
      "dst": ["tag:hasee"],
      "ip": ["22", "3389"]
    }
  ]
}
```

要点：

- **用户**写 `"用户名@"`（带 @）；**标签**写 `"tag:xxx"`
- 自动组：`autogroup:member`（全部个人设备）、`autogroup:tagged`（全部打标设备）、
  `autogroup:self`（仅同一用户自己的设备间）
- 目的端可写标签、用户、具体 IP（`"100.64.0.3"`）或 CIDR
- `ip` 填 `"*"` 或端口列表 `["80", "443", "22"]`
- **原理提醒**：一旦写入策略，未命中任何规则（且无兜底规则）的流量即被拒绝——
  收紧时务必给管理员自己的设备留全通规则，否则会把自己锁在外面

## 3. 通过 API 写入与验证

```bash
curl -sk -X PUT https://<你的域名>/api/v1/policy \
  -H "Authorization: Bearer <API Key>" -H "Content-Type: application/json" \
  -d '{"policy":"<转义后的策略 JSON 字符串>"}'

curl -sk https://<你的域名>/api/v1/policy -H "Authorization: Bearer <API Key>"
# 未设置时返回：loading ACL from database: acl policy not found（属正常，且此时=允许全部）
```

> Web UI「访问控制 / Access controls」页有图形化编辑器（规则/组/标签），适合日常调整。
> 改完策略后客户端下次同步即生效，一般无需重启。
