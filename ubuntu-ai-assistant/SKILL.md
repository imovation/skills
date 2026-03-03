# ubuntu-ai-assistant (Skill Definition)

此 Skill 专为协助 Ubuntu 24.04.4 LTS (AMD64) 新手在 Windows 远程桌面 (RDP) 环境下开发 AI (OpenCode/OpenClaw) 而设计。

## 环境基准
- **OS:** Ubuntu 24.04.4 LTS
- **Access:** Windows Remote Desktop (XRDP)
- **Primary Use:** AI Development (OpenCode, OpenClaw)

## 1. Ubuntu 基础操作 (RDP 优化版)
新手在 RDP 下最常见的问题是黑屏、卡顿或 Session 冲突。

### 1.1 系统更新与基础工具
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git vim htop build-essential
```

### 1.2 RDP 环境检查
...
### 1.3 路径管理与工作空间 (新手必看)
...
### 1.4 RDP 剪贴板与图片粘贴 (正式解决方案)
在 Ubuntu 24.04 的 RDP (GNOME Remote Desktop) 环境下，直接粘贴截图可能失效。
- **原因**: 远程剪贴板数据（DIB/PNG）进入本地 X11 Session 时未能正确触发应用的粘贴事件。
- **解决方案**: 使用 `scripts/rdp-clipboard-bridge.py` 脚本。该脚本会监控剪贴板，发现 RDP 传输的图片或文件后，立即将其重注入本地剪贴板。
- **自动运行**: 已配置在 `~/.config/autostart/rdp-clipboard-bridge.desktop`，开机即生效。

## 2. AI 开发工具 (OpenCode/OpenClaw)
...
## 3. 进化铁律 (Dynamic Evolution Loop)
...
5. **部署**: 仅在用户授权后运行 `scripts/deploy_skill.sh`。
6. **归档**: 每次进化必须标注解决问题的 AI 模型名称，并同步至 GitHub。
7. **严禁瞎猜**: 若不理解描述或存在歧义，必须明确后再执行。


## 4. 进化记录 (Evolution History)
- **[2024-03-03] RDP 图片粘贴修复**
  - **解决模型**: `antigravity-gemini-3-flash`
  - **内容**: 解决了 Ubuntu 24.04 RDP 环境下无法粘贴截图/文件的问题，通过 xclip 重注入实现。



