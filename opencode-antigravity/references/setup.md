# 安装与首次配置（离线安装模式）

本技能 assets/ 内附本地安装包 `opencode-antigravity-auth-1.6.0.tgz`（离线兜底；日常更新走 `@latest` 包缓存，见 architecture.md）。

## 第一阶段：自动安装（AI 用工具直接执行）

1. **安装插件包**：在 `~/.config/opencode` 目录下执行
   ```bash
   cd ~/.config/opencode && npm install ~/.config/opencode/skills/opencode-antigravity/assets/opencode-antigravity-auth-1.6.0.tgz
   ```
   注意：若 `~/.cache/opencode/packages/` 已有 @latest 缓存，实际加载的是缓存副本（详见 architecture.md），npm 安装主要用于首装与离线场景。

2. **注入配置**：读取并修改 opencode 配置（`~/.config/opencode/opencode.jsonc` 或 `opencode.json`），确保根对象含：
   ```jsonc
   { "plugin": [ "opencode-antigravity-auth" ] }
   ```
   已存在则跳过。当前机器使用的是 `opencode.jsonc` 且已配置。

## 第二阶段：引导用户完成 OAuth 登录（输出指导）

1. 终端执行：
   ```bash
   opencode auth login
   ```
2. 菜单中选择 **OAuth with Google (Antigravity)**。
   ⚠️ **不要选默认的 "Google"**——如果被要求 "Enter your API key"，说明插件安装/配置未生效，回到第一阶段排查。
3. 浏览器授权成功后，模型配置询问建议选 **"Configure models in opencode.json"**（自动写入全部受支持模型）。
4. 多账号：多次运行 `opencode auth login` 绑定多个 Google 账号，插件自动轮换（池文件见 architecture.md）。
5. 验证：
   ```bash
   opencode run "你好，请自我介绍一下。" --model=google/antigravity-gemini-3.1-pro
   ```

## 安装期排错

| 症状 | 处置 |
|------|------|
| `Address Already in Use`（端口 51121） | 找到并结束占用 51121 的进程 |
| 登录后要求输入 API key | 插件未生效：核对 plugin 数组与 npm 安装位置 |
| 装好后某模型不可用/挂起 | 见 troubleshooting.md（端点策略、UA 门禁、变体重试补丁）|
