---
name: opencode-model-manager
description: 管理和切换 OpenClaw 环境下 opencode 的 LLM 模型。当用户需要更改模型、修复模型回退问题（如变成 big-pickle）或为 opencode 会话配置特定模型时，请使用此技能。
---

# OpenCode 模型管理器 (OpenCode Model Manager)

此 Skill 用于管理 opencode 的模型配置，特别是在 OpenClaw (Element) 环境中运行时，确保模型切换生效并防止意外降级。

## 核心概念

- **双层配置体系**：opencode 优先读取项目本地配置 `~/.opencode/opencode.json`，其次是全局配置 `~/.config/opencode/opencode.json`。在 OpenClaw 环境中，应优先修改本地配置。
- **降级回退 (Fallback)**：若指定的模型初始化失败（如插件 Bug、鉴权失效），opencode 会静默回退至内置的 `big-pickle` 模型。
- **关键插件**：使用 `google/antigravity-*` 系列模型必须确保 `opencode-antigravity-auth` 插件已安装且源码中的 `proper-lockfile` 导入逻辑已修正为 `import * as lockfile`。

## 工作流程

### 1. 修改模型配置
1. 读取 `~/.opencode/opencode.json`（若不存在则读取全局配置）。
2. 在 JSON 根目录下更新 `"model"` 字段的值为目标模型 ID。
3. 保存文件。

### 2. 故障排查：解决回退到 "big-pickle" 的问题
若切换后 Agent 仍自称是 "big-pickle"：
1. **修复插件源码**：检查 `~/.opencode/node_modules/opencode-antigravity-auth/dist/src/plugin/storage.js`，确保 `lockfile` 的导入语法为 `import * as lockfile from "proper-lockfile";`。
2. **校验鉴权**：运行 `opencode providers ls` 确认 Google 凭据显示为已登录状态。

## 常用模型 ID 参考

### Antigravity 高性能模型 (需插件)
- **Gemini 3.1 Pro**: `google/antigravity-gemini-3.1-pro`
- **Gemini 3 Pro**: `google/antigravity-gemini-3-pro`
- **Gemini 3 Flash**: `google/antigravity-gemini-3-flash`
- **Claude Sonnet 4.6**: `google/antigravity-claude-sonnet-4-6`
- **Claude Opus 4.6 Thinking**: `google/antigravity-claude-opus-4-6-thinking`

### OpenCode 免费模型
- **GPT-5 Nano**: `opencode/gpt-5-nano`
- **Qwen 3.6 Plus (Free)**: `opencode/qwen3.6-plus-free`
- **MiniMax M2.5 (Free)**: `opencode/minimax-m2.5-free`
- **Nemotron 3 Super (Free)**: `opencode/nemotron-3-super-free`
- **Big Pickle (默认备份)**: `opencode/big-pickle`

## Element 验证指导 (详细步骤)

更改配置后，请务必按照以下步骤在 Element 客户端中进行验证，以确保 ACP 会话已完全刷新：

1. **重置当前会话上下文**：
   在聊天框中输入并发送命令：
   ```text
   /new
   ```
   *预期响应：应看到 OpenClaw 回复 "ACP session reset in place."。*

2. **重新启动 Agent**：
   输入您常用的启动命令（根据您的目录调整）：
   ```text
   /acp spawn opencode --mode persistent --bind here --cwd /home/imovation/shining
   ```
   *预期响应：应看到 "Spawned ACP session agent:opencode..." 的绿色勾选提示。*

3. **身份与模型确认**：
   直接向启动后的 Agent 提问：
   ```text
   你是谁？你现在在使用什么模型？请给出完整模型 ID。
   ```
   *验证要点：*
   - 如果它回答是 **Antigravity** 并且模型 ID 包含 **antigravity-gemini-3.1-pro**，则切换成功。
   - 如果它回答是 **OpenCode 助手** 并且提到 **big-pickle**，说明配置未生效或触发了降级，请检查插件修复情况。
