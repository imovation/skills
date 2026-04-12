---
name: openclaw-matrix-acp-dedupe
description: |
  修复 OpenClaw Matrix 渠道的 ACP（Agent Client Protocol）会话重复回复问题。
  
  当 OpenClaw 通过 Matrix 渠道使用 ACP 会话（如 OpenCode、Claude Code、Codex 等）
  时，每条回复会被发送两次——一次作为流式 block 消息，一次作为 final 回退消息。
  这是因为 Matrix 插件缺少 shouldTreatDeliveredTextAsVisible 方法，
  导致 OpenClaw 的 ACP 投递逻辑误判 block 消息不可见，触发 fallback 重复发送。

  适用场景：用户提到 OpenClaw ACP 重复回复、Matrix 双重消息、OpenCode/ACP 
  在 Element 中回复两条、ACP 消息去重、Matrix ACP dedup 等问题时，应使用此 skill。
  即使问题描述不精确（如"Matrix 里机器人发重复了""为什么回复两遍"），
  只要涉及 OpenClaw + Matrix + ACP，都应触发此 skill。
metadata:
  openclaw:
    emoji: "🔧"
    requires:
      anyBins: ["openclaw"]
---

# OpenClaw Matrix ACP 重复回复修复

## 问题背景

OpenClaw 的 ACP 消息投递有两条独立路径：

1. **Block reply 路径** — `sendBlockReply()` 将文本增量/完整内容发送到 Matrix
2. **Final fallback 路径** — `finalizeAcpTurnOutput()` 在回合结束时检查"是否已有可见文本投递"，如果没有则补发一次完整内容

关键判断逻辑（`dispatch-acp-*.js` 第 769 行附近）：

```javascript
if (!params.delivery.hasDeliveredVisibleText() || 
    params.delivery.hasFailedVisibleTextDelivery()) {
    // 重新发送 accumulatedBlockText → 重复！
}
```

`hasDeliveredVisibleText()` 会通过每个渠道插件的 `shouldTreatDeliveredTextAsVisible` 方法判断 block reply 是否"可见"：

| 渠道 | override | 结果 |
|------|----------|------|
| Discord | ✅ `kind === "block" && text.trim().length > 0` | block 算可见，不重复 |
| Telegram | ✅ `kind !== "final"` | 非 final 算可见，不重复 |
| Matrix | ❌ **无 override** | 默认返回 `false`，触发 fallback → **重复发送** |

## 修复方案

在 Matrix 插件的 `outbound` 对象中添加 `shouldTreatDeliveredTextAsVisible` 方法，
与 Discord 逻辑一致，让 block reply 被正确标记为"已投递可见文本"，阻止 fallback 重复发送。

## 修复步骤

以下步骤优先使用自动化脚本（`scripts/patch-matrix-dedupe.sh`），但也可以手动操作。

### 自动化修复（推荐）

```bash
bash scripts/patch-matrix-dedupe.sh --apply
```

### 手动修复

#### 第一步：定位 Matrix 插件文件

```bash
OPENCLAW_DIR=$(dirname $(dirname $(which openclaw)))/lib/node_modules/openclaw
MATRIX_PLUGIN=$(find "$OPENCLAW_DIR/dist" -name 'channel-BT7*.js' -o -name 'channel-*matrix*.js' 2>/dev/null | head -1)
```

> ⚠️ 文件名中的哈希后缀会随版本变化。如果上面的 find 没有结果，
> 尝试在 `dist/` 目录下搜索包含 `matrixPlugin` 且包含 `outbound` 的 JS 文件。

#### 第二步：检查当前是否需要修补

在文件中搜索 `shouldTreatDeliveredTextAsVisible`。如果 Matrix 插件的 `outbound` 对象中
已经有此方法，说明此版本已修复，无需操作。

如果 **没有找到**，或虽然有但在 Matrix 的 `outbound` 对象之外（例如是另一个渠道插件的方法），
则需要继续修补。

#### 第三步：执行修补

找到 Matrix 插件中 `outbound` 对象的位置。它看起来像这样：

```javascript
outbound: {
    deliveryMode: "direct",
    chunker: chunkTextForOutbound,
    // ... 其他属性
}
```

在 `outbound: {` 之后的 `deliveryMode` 行后面，添加 `shouldTreatDeliveredTextAsVisible` 方法：

```javascript
outbound: {
    deliveryMode: "direct",
    shouldTreatDeliveredTextAsVisible: (params) => params.kind === "block" && typeof params.text === "string" && params.text.trim().length > 0,
    chunker: chunkTextForOutbound,
    // ... 其他属性保持不变
}
```

#### 第四步：重启 Gateway

```bash
openclaw gateway restart
```

#### 第五步：验证

检测修补是否生效：

```bash
grep "shouldTreatDeliveredTextAsVisible" "$MATRIX_PLUGIN"
```

应能看到方法已添加到 Matrix 的 `outbound` 对象中。

## 升级后重新应用

OpenClaw 升级（`npm update -g openclaw` 或 `pnpm update -g openclaw`）会覆盖 `dist/` 目录，
导致修补丢失。升级后需要：

```bash
bash scripts/patch-matrix-dedupe.sh --apply
openclaw gateway restart
```

或者手动重新执行"第三步"的修补。

### 自动化升级钩子（可选）

如果希望升级后自动修补，可以在 OpenClaw 的 `hooks` 配置中添加启动钩子：

```json5
// ~/.openclaw/openclaw.json
{
  hooks: {
    internal: {
      entries: {
        "matrix-acp-dedupe-patch": {
          enabled: true,
          // 注意：OpenClaw 目前不直接支持 post-update 钩子
          // 此处仅为文档记录，实际需手动或通过系统级钩子实现
        }
      }
    }
  }
}
```

更实用的方案是创建 systemd 或 cron 的 post-update 脚本，或者在每次手动升级后
运行 `bash scripts/patch-matrix-dedupe.sh --apply`。

## 配置影响说明

此修补不影响 OpenClaw 的任何配置项。它仅修改运行时 JS 文件中的渠道插件行为。

以下常见配置与此修补**无关**：

| 配置项 | 用途 | 是否与此修补相关 |
|--------|------|------------------|
| `acp.stream.deliveryMode` | ACP 消息流式模式 | ❌ 无关 |
| `acp.stream.repeatSuppression` | ACP 重复状态抑制 | ❌ 无关（仅抑制工具状态重复，不影响消息路径重复） |
| `channels.matrix.streaming` | Matrix 流式预览 | ❌ 无关 |
| `plugins.entries.acpx.config.dedupe` | acpx 去重 | ❌ 不存在此配置项 |
| `plugins.entries.acpx.config.*` | acpx 运行时配置 | ❌ 无关 |

## 工具脚本

- `scripts/patch-matrix-dedupe.sh` — 自动检测、修补、回滚的 shell 脚本

## 参考资料

- `references/root-cause-analysis.md` — 根因分析的详细技术文档，包含源码定位和行为对比