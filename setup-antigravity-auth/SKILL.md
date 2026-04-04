---
name: setup-antigravity-auth
description: "帮助用户自动安装 opencode-antigravity-auth 插件并完成配置文件修改，然后引导用户使用 Google OAuth 登录。当用户要求安装、配置或使用 antigravity 插件时触发此技能。"
---

# 配置 Opencode Antigravity 认证插件（全自动安装模式）

本技能内部随附了该插件的本地安装包。当用户触发此技能时，**你（AI 助手）需要主动调用工具**来帮用户在系统中安装插件并修改配置文件，然后再通过语言指导用户完成后续的终端交互。

## 第一阶段：自动安装与配置（你必须使用工具自动执行）

**你需要立即执行以下动作序列（使用 Bash / 读取 / 写入 等工具）：**

1. **自动安装插件包**：
   - 定位安装包的绝对路径：`~/.config/opencode/skills/setup-antigravity-auth/assets/opencode-antigravity-auth-1.6.0.tgz` （根据用户系统展开 `~`）。
   - 调用 Bash 工具，使用 npm 安装该压缩包，使其作为环境的依赖。可以在用户的 `~/.config/opencode` 目录下执行 `npm install <安装包的绝对路径>`。
   
2. **自动读取并修改配置**：
   - 读取文件 `~/.config/opencode/opencode.json`。如果该文件不存在，请使用写入工具创建。
   - 解析 JSON 内容，确保根对象中有一个 `plugin` 数组。
   - 将插件名称 `"opencode-antigravity-auth"` 添加到 `plugin` 数组中。如果数组中已包含，则忽略。
   - 将修改后的内容写回 `opencode.json`。配置的格式应该类似如下：
     ```json
     {
       "plugin": [
         "opencode-antigravity-auth"
       ]
     }
     ```

**完成上述所有自动化操作后，向用户汇报你已经成功安装了插件包并完成了 JSON 注入，接着进行下面的引导。**

---

## 第二阶段：指导用户后续操作（向用户输出指导）

自动安装和配置完成后，请用清晰、分步骤的语言指导用户完成后续操作：

### 1. 登录与认证
告诉用户在终端中运行以下命令开始认证：
```bash
opencode auth login
```

### 2. 选择正确的服务商选项
向用户解释命令行会弹出一个菜单。他们必须选择 **OAuth with Google (Antigravity)** 选项。
> **重要提示：** 请着重提醒用户**不要**选择默认的“Google”选项。如果命令行要求“Enter your API key”（输入 API 密钥），说明刚才的配置或安装没有成功生效。

### 3. 一键配置模型
告知用户，在浏览器授权登录成功后，终端会询问如何配置模型。建议选择 **"Configure models in opencode.json"**。这会自动将所有受支持的模型（如 Gemini 3.1 Pro 和 Claude 4.6）写入配置中，无需手动处理。

### 4. 验证测试
提供一个测试命令，让用户验证环境是否就绪：
```bash
opencode run "你好，请自我介绍一下。" --model=google/antigravity-gemini-3.1-pro
```

## 常见问题排错（Troubleshooting）
如果用户反馈报错，请利用以下知识进行解答：
- **端口冲突（Address Already in Use）：** 说明端口被占用。建议找出并终止正在使用 `51121` 端口的进程。
- **多账号限流：** 如果出现 Rate Limit 相关限制，用户可以多次运行 `opencode auth login` 来绑定多个 Google 账号，插件会自动在账号间进行轮询。