# 架构与账号体系

## 请求链路

```
opencode core (ai-sdk, provider=google)
  → 请求 generativelanguage.googleapis.com/v1beta/models/<id>:streamGenerateContent
  → 插件 fetch 钩子拦截(dist/src/plugin.js)
  → 改写为 {endpoint}/v1internal:streamGenerateContent?alt=sse
    body = {project, model(wire名), request:{...Gemini体}}
  → 端点回退链: daily → autopush → prod
```

- opencode 核心不认识的模型 ID 会被替换为默认别名 `gemini-flash-latest`（标题生成等 small 请求也用它）——插件拿不到原始名字。
- 会话粘性头：`x-session-id` / `x-session-affinity`。

## 文件位置

| 文件 | 作用 |
|------|------|
| `~/.local/share/opencode/auth.json` | 活动凭据，键 `google`，refresh 三段式 |
| `~/.config/opencode/antigravity-accounts.json` | 多号池(v4)，含 fingerprint/rateLimitResetTimes |
| `~/.cache/opencode/packages/opencode-antigravity-auth@latest/` | **实际加载的插件代码**（补丁打这里） |
| `~/.config/opencode/antigravity-logs/` | `OPENCODE_ANTIGRAVITY_DEBUG=1` 时的调试日志 |
| `/home/imovation/antigravity-accounts/<邮箱>/` | 用户手动备份的历史账号池 |

## 账号切换/导入

活动凭据优先于池。切号两种方式：

1. 改 auth.json（立即生效，新进程）：
   ```json
   "google": {"type":"oauth","refresh":"<refreshToken>|<projectId>|<managedProjectId>","access":"","expires":0,"email":"x@gmail.com"}
   ```
2. TUI 里重新 OAuth 登录。

池条目字段：email/refreshToken/projectId/addedAt/lastUsed/enabled(/managedProjectId/fingerprint)。轮换仅在限流信号出现时发生；**改池不会自动切换活动凭据**。

## 与 pi 互通

- refresh 三段式格式完全一致，可直接互导。
- pi 侧键名为 `google-antigravity`（`~/.pi/agent/auth.json`），单账号制。
- pi 的扩展(`@cortexkit/pi-antigravity-auth`)与本插件同源分叉，OAuth client 相同，端点策略不同（见 troubleshooting §端点）。
