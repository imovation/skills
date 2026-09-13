---
name: opencode-antigravity
description: 管理 opencode 的 antigravity 认证插件（opencode-antigravity-auth）全生命周期运维——安装/首次配置/OAuth 登录引导，以及故障诊断、补丁维护与账号管理。当用户提到 opencode 中 antigravity/Gemini 模型相关任何问题时都应触发——"opencode 里 Gemini 3.x Flash 不可用/报错/挂起""antigravity 认证失败""模型列表缺失""SUBSCRIPTION_REQUIRED/VALIDATION_REQUIRED/429 配额""切换或导入 antigravity 账号""插件升级后坏了"等；当用户要求**安装 antigravity 插件、配置 antigravity 认证/登录**时也必须触发本技能。也覆盖 opencode 与 pi 之间 antigravity 账号凭据互通。
---

# opencode Antigravity 插件运维

管理 `opencode-antigravity-auth` 插件的故障诊断、补丁维护与账号管理。

## 启动流程

### 1. 补丁状态检测

```bash
bash scripts/check-plugin-patch.sh            # 输出 PATCHED / VANILLA / NOT_FOUND
bash scripts/check-plugin-patch.sh --fix      # 自动恢复变体重试补丁
```

**插件更新/`opencode upgrade` 后必须复查**——补丁打在包缓存副本上，会被覆盖。

### 2. 意图路由

| 症状 | 参考 |
|------|------|
| 安装插件 / 首次配置 / OAuth 登录引导 | references/setup.md |
| 某些模型报错、其他正常 | references/troubleshooting.md §模型级错误 |
| 全部模型挂起/无响应 | references/troubleshooting.md §挂起类 |
| 认证/账号/切换/导入 | references/architecture.md §账号体系 |
| 请求内容不明、需要抓包 | references/troubleshooting.md §诊断工具箱 |

## 核心事实（先读这个）

1. **端点决定生死**：Google 免费额度限制部署在 prod 端点；daily 沙箱端点宽松但**模型清单分钟级动态漂移**（同一模型时通时不通，3.5/3.6/3.7 轮流上下线）。
2. **wire 名带思考后缀**：daily 上实体名形如 `gemini-3.7-flash-low/high`、`gemini-3.5-flash-low`；裸名和别名（`gemini-flash-latest`）经常 404。
3. **UA 指纹门禁**（2026-08-25 实证）：daily 按 User-Agent 放行模型实体——`antigravity/cli/1.1.13 (...)` 可用，IDE 风格 `antigravity/2.0.x darwin/win32` 会 404。已用 UA 覆写补丁解决。
4. **限流中毒**：prod 的 429 会把账号标记进 `rateLimitResetTimes`，之后该账号全模型被拒并进入最长 300s 的等待循环（表现为挂起）。配置 `~/.config/opencode/antigravity.json` 的 `max_rate_limit_wait_seconds: 20` 可快速失败；清标记=删池文件中该字段。
5. **模型需在 opencode.jsonc 定义**：未定义的模型 ID 核心会替换为别名导致插件拿不到真名 → UnknownError。定义含 variants 后核心才传真名。
6. 已装补丁（scripts/check-plugin-patch.sh 检测+恢复）：①变体重试（404/429/403 时轮换候选名）②UA 覆写为 cli 风格。
3. **插件加载自包缓存**：实际执行的是 `~/.cache/opencode/packages/opencode-antigravity-auth@latest/`，改 `~/.config/opencode/node_modules/` 无效。
4. **双账号体系**：活动凭据在 `~/.local/share/opencode/auth.json`（键 `google`）；多号轮换池在 `~/.config/opencode/antigravity-accounts.json`。池只是备选，活动凭据优先。
5. 与 pi 的凭据通用：refresh 三段式 `refreshToken|projectId|managedProjectId` 两边一致，可互导（见 references/architecture.md）。
