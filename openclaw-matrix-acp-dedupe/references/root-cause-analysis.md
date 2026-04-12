# OpenClaw Matrix ACP 重复回复 — 根因分析

## 症状

在 Matrix（Element）渠道中使用 ACP 会话（如 `/acp spawn opencode --bind here`）时，
每条来自 ACP 智能体的回复都会被发送两次，内容完全相同。

示例：
```
用户: 你好，用什么模型？
机器人: 我是 opencode，当前使用的模型是 big-pickle。
       我是 opencode，当前使用的模型是 big-pickle。
       ⚙️ Session ids resolved.
```

## 根因

### ACP 消息投递机制

OpenClaw 的 ACP 消息投递有两条独立路径：

1. **Block reply 路径** — 通过 `sendBlockReply()` 将文本作为增量/完整消息发送到渠道
2. **Final fallback 路径** — 通过 `finalizeAcpTurnOutput()` 在回合结束时检查是否需要补发

### Final fallback 触发条件

在 `dispatch-acp-Bp1dZnlM.js` 第 769 行：

```javascript
if (ttsMode !== "all" && hasAccumulatedBlockText && !finalMediaDelivered &&
    !params.delivery.hasDeliveredFinalReply() &&
    (!params.delivery.hasDeliveredVisibleText() ||
     params.delivery.hasFailedVisibleTextDelivery())) {
    const delivered = await params.delivery.deliver(
        "final", { text: accumulatedBlockText }, { skipTts: true }
    );
}
```

关键判断：`hasDeliveredVisibleText()` — 是否已有"可见文本"被成功投递。

### `shouldTreatDeliveredTextAsVisible` 的作用

`hasDeliveredVisibleText()` 通过每个渠道插件的 `shouldTreatDeliveredTextAsVisible` 方法
判断 block reply 是否算"可见"：

**Discord**（`channel-CIcZEg_v.js:222`）：
```javascript
function shouldTreatDiscordDeliveredTextAsVisible(params) {
    return params.kind === "block" && typeof params.text === "string" && params.text.trim().length > 0;
}
```

**Telegram**（`channel-ClQq9jsV.js:516`）：
```javascript
// params.kind !== "final" → 所有非 final 投递都算可见
```

**Matrix**（`channel-BT7IEUCR.js:1120`）：
```javascript
outbound: {
    deliveryMode: "direct",
    // ❌ 缺少 shouldTreatDeliveredTextAsVisible
    chunker: chunkTextForOutbound,
    // ...
}
```

### 默认行为导致的重复

当渠道插件没有提供 `shouldTreatDeliveredTextAsVisible` override 时，
`dispatch-acp` 中的默认逻辑（第 480 行附近）：

```javascript
async function shouldTreatDeliveredTextAsVisible(params) {
    // ...
    const channelId = normalizeOptionalLowercaseString(params.channel);
    if (!channelId) return false;
    const outbound = getChannelPlugin(channelId)?.outbound;
    const visibilityOverride = outbound?.shouldTreatDeliveredTextAsVisible
        ?? outbound?.shouldTreatRoutedTextAsVisible;
    if (visibilityOverride) return visibilityOverride({ kind, text });
    if (!params.routed) return channelId === "telegram"; // 仅 Telegram 在默认情况下算可见
    return false; // Matrix 走到此处 → 返回 false
}
```

结果：
1. Block reply 被正常发送到 Matrix ✅
2. `hasDeliveredVisibleText()` 返回 `false`（Matrix 没有 override）
3. Final fallback 触发，将相同的 `accumulatedBlockText` 再次发送 ❌

### 为什么 Discord/Telegram 不受影响

- Discord：`shouldTreatDeliveredTextAsVisible` 在 block text 非空时返回 `true`
  → `hasDeliveredVisibleText()` = true → 不触发 fallback
- Telegram：非 final 投递都算可见 → 也不触发 fallback

### 为什么 `repeatSuppression` 无法解决

`repeatSuppression`（`acp.stream.repeatSuppression`）仅作用于 ACP 回复投影器内部，
用于去重相同状态文本（如工具调用的 `started`/`completed` 事件）。

它**不**干预 block reply 路径和 final fallback 路径之间的重复——这是两个
完全不同的投递"类型"（kind: "block" vs kind: "final"），通过不同的 dispatcher 方法发送。

### 为什么 `deliveryMode: "final_only"` 无法解决

`deliveryMode: "final_only"` 仅控制 block chunk 的**增量投递**时机：
- `final_only`：block chunk 在回合结束时一次性 flush
- `live`：block chunk 实时流式投递

无论哪种模式，`finalizeAcpTurnOutput()` 的 fallback 逻辑都会执行。
如果 `hasDeliveredVisibleText()` 返回 false，final 消息都会被发送。

## 修补

在 Matrix 插件的 `outbound` 对象中添加 `shouldTreatDeliveredTextAsVisible`：

```javascript
outbound: {
    deliveryMode: "direct",
    shouldTreatDeliveredTextAsVisible: (params) =>
        params.kind === "block" && typeof params.text === "string" && params.text.trim().length > 0,
    chunker: chunkTextForOutbound,
    // ... 其他属性
}
```

这使 Matrix 的 block reply 被正确标记为"已投递可见文本"，阻止 fallback 重复发送。

## 影响范围

- 仅影响 Matrix 渠道的 ACP 会话回复（OpenCode、Claude Code、Codex 等）
- 不影响 Matrix 的原生智能体回复（非 ACP 路径不经过此逻辑）
- 不影响 Discord、Telegram 等其他渠道（已有 override）
- 不影响 `/acp spawn` 以外的 Matrix 消息

## 持久性

此修补直接修改 OpenClaw 的编译产物（`dist/` 目录下的 JS 文件）。
OpenClaw 升级（npm/pnpm update）会覆盖 `dist/` 目录，导致修补丢失。

升级后需要重新应用修补，可通过 `scripts/patch-matrix-dedupe.sh --apply` 自动完成。