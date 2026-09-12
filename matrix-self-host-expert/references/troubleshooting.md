# Synapse 故障排查

主流程见 `SKILL.md`。本文档收录常见"地雷"、媒体 404 的完整原理与限速说明。

## 常见"地雷"修复表

| 错误 | 原因 | 修复 |
|------|------|------|
| `ConfigError` | 仅开了 `enable_registration` | 加 `enable_registration_without_verification: true` |
| `IncorrectDatabaseSetup` | Postgres 非 C locale | `database` 块加 `allow_unsafe_locale: true` |
| Permission denied | synapsedata 属主非 991 | `chown -R 991:991 ./synapsedata` |
| 502 Bad Gateway | Synapse 首次 DB 迁移约 20-30s | 等待后观察 `docker logs matrix-synapse` |
| `M_LIMIT_EXCEEDED` | 触发 Synapse 限速（Element 快速重连/批量操作时常见） | 按 `assets/homeserver-snippets.yaml` 的 `rc_*` 放宽，稳定后调回；同时确认不是恶意刷接口 |
| 媒体上传返回 MXC URI 但下载全 404 | 见下节 | `enable_authenticated_media: false` |

## 媒体上传成功但下载 404（v1.120+ 高频）

现象：上传返回 MXC URI，文件在磁盘且 DB 记录正常，但所有下载 404。

原因：`enable_authenticated_media` 自 Synapse v1.120 起默认 `true`（该配置 v1.100 引入，v1.100~v1.119 默认 false；官方 release notes 确认 v1.120.0 起强制认证媒体）。媒体被标记 `authenticated=true`，未认证的旧下载接口被拒绝：

- `/_matrix/media/v3/download/...` 返回 404
- `/_matrix/client/v1/media/download/...` 带上 access_token 可正常返回 200

修复：在 `homeserver.yaml` 添加 `enable_authenticated_media: false` 后重启 Synapse。

验证：

```bash
docker exec matrix-synapse grep enable_authenticated_media /data/homeserver.yaml
docker compose restart synapse
```
