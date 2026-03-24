---
name: rdp-manager
description: 万能远程桌面管理工具。当用户提到远程连接断开、0x904 报错、物理机黑屏、或者想要在 Ubuntu 24.04 的内置登录 (gnome-remote-desktop) 与稳定模式 (xrdp) 之间切换时，请务必启用此技能。它能自动处理证书生成、端口占用和会话冲突。
---

# RDP Manager (远程桌面全能管理器)

## 前置条件 (Prerequisites)
为确保本技能正常运行，目标系统需满足以下条件：
- **系统版本**：Ubuntu 24.04 (Noble Numbat) 及以上。
- **必需工具**：`sudo`, `python3`, `xclip` (用于剪贴板), `openssl` (用于证书修复)。
- **服务支持**：`systemd`, `gnome-remote-desktop`。
- **权限要求**：当前用户需具备 `sudo` 执行权限。

## 场景 A：切换至内置远程登录 (Built-in)
- **触发场景**：想体验 24.04 的官方功能，或者测试 Wayland 下的显示效果。
- **操作指令**：
  - 运行脚本：`python3 scripts/switch_to_builtin.py`。
- **后续关键操作 (必做！)**：
  1. **确认开关开启**：打开 Ubuntu 的【设置】 -> 【系统】 -> 【远程登录】，确保顶部开关处于【开启】状态。
  2. **自定义凭据**：点击“铅笔”图标，设置并记下用户名和密码。
  3. **物理机注销**：点击右上角“注销 (Log Out)”，回到系统登录界面。
- **注意**：如果不注销物理登录，远程会话会与物理 session 冲突，导致 0x904 报错或黑屏。


## 场景 B：切换至稳定 Xorg 模式 (xrdp)
- **触发场景**：内置方案崩溃、黑屏，或追求长期稳定的远程生产力。
- **操作指令**：
  - 运行脚本：`python3 scripts/switch_to_xrdp.py`。
- **关键操作**：在物理机上**必须注销（Log Out）**，否则会产生会话冲突。

## 故障修复 (Troubleshooting)
1. **剪贴板同步失效**：
   - 运行：`pgrep -f rdp-clipboard-bridge.py > /dev/null || python3 ~/agent-skill-factory/projects/ubuntu-tutor/assets/rdp-clipboard-bridge.py &`。
2. **黑屏问题**：
   - 检查并修改 `/etc/xrdp/startwm.sh`，确保开头包含：
     ```bash
     unset DBUS_SESSION_BUS_ADDRESS
     unset XDG_RUNTIME_DIR
     ```
3. **内存溢出崩溃**：
   - 检查 `/etc/systemd/system/gnome-remote-desktop.service.d/override.conf` 是否包含 `Environment=GRD_RDP_DISABLE_HWACCEL=1`。

## 安全建议
- **公网暴露**：请勿直接将 3389 映射至公网。
- **推荐策略**：将路由器上的高位随机端口（如 53389）映射至笔记本的 3389 端口。
