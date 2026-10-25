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
   - 服务状态：`systemctl --user status rdp-clipboard-bridge.service`（开机自启、崩溃自动重启，不依赖终端进程）。
   - 手动拉起：`systemctl --user restart rdp-clipboard-bridge.service`；日志：`journalctl --user -u rdp-clipboard-bridge -f`。
   - 说明：桥接脚本为 `scripts/rdp_bridge.py`，以 systemd user service（`rdp-clipboard-bridge.service`）常驻；负责把 RDP 客户端带来的 `image/bmp` 转换为 `image/png`，修复截图粘贴失效（opencode TUI 等只认 `image/png`）。
   - **文件复制一律不碰**：剪贴板一旦带有 `text/uri-list` 或 `x-special/gnome-copied-files`，桥接必须原样放过，交给 gnome-remote-desktop 的 CLIPRDR 文件传输。历史版本会把复制的图片文件改写成纯 `image/png`，导致“桌面/文件管理器复制文件 → Windows 粘贴”失效（2026-10-25 修复并加守卫）。
   - **桌面复制文件到 Windows 粘贴无反应**：先确认 `dpkg -l gnome-remote-desktop` 是 `+fix5` 或更高（修复“仅提供 `x-special/gnome-copied-files` 的来源被丢弃”的问题）；再确认桥接没有改写文件剪贴板（见上）。
   - **桥接必须自己找到 X display**：本服务以 `systemd --user` 运行，进程环境里既没有 `DISPLAY` 也没有 `XAUTHORITY`。脚本会按权威性依次探测并**逐一验证连通性**：进程环境 → `systemctl --user show-environment` → `loginctl` 活跃会话的 `Display` → 本用户自己拥有的 `/tmp/.X11-unix/X*`（自动跳过 gdm 的 `:0` 和 GNOME 设置对话框）。display 失效（注销、xrdp 重连、重启）时连续失败 3 次会自动重新探测并打印切换日志。
   - **启动日志必须确认这一行**：`journalctl --user -u rdp-clipboard-bridge | grep 已启动`，确认 `DISPLAY=` 是当前图形会话的 display（Wayland 会话通常是 `:1`，xrdp 通常是 `:10`），且 `XAUTHORITY` 非空。
   - **粘贴图片失败时的判断依据**：opencode V2 的 TUI 只通过 `libopentui.so` 原生剪贴板读取，且**只接受 `image/png` 和 `text/plain`**；剪贴板上只有 `image/bmp` 时会直接报错 `X11 clipboard property transfer failed`，看到这个报错 = 桥接没生效，先查桥接日志而不是 opencode。
   - **`Clipboard read timed out` 的含义**：原生读取的硬超时是 **1000ms**（opencode 侧不可配）。X11 协议下，若剪贴板 selection **没有属主**，服务器会把 `ConvertSelection` **直接丢弃、不回 SelectionNotify**，opencode 只能空等到超时——注意这和"属主在但没有 image/png"（报 `X11 clipboard property transfer failed`）是**两种不同的故障**。桥接会在检测到无属主时自动重新发布上一张图，日志为 `[Bridge] 剪贴板已无属主，已重新发布 image/png`。
   - **踩过的坑（改这块时务必注意）**：探测 TARGETS 必须用 `subprocess.run` 并自己判断 returncode，**不能用 `subprocess.check_output`**——剪贴板无属主时 xclip 以 rc=1 退出，check_output 会直接抛 `CalledProcessError`，自愈分支根本走不到，表现就是"自愈代码写了但永远不生效"。
   - **Wayland 会掩盖这个问题**：本机 GNOME/Wayland 下有 XWayland 兜底，xclip 属主被杀后剪贴板会立刻被 XWayland 接管，看起来一切正常；只有 xrdp 这种纯 X11 会话才会真正暴露。要在本地验证请用 `Xvfb :99`（无合成器）复现。
   - **不要让桥接反复抢剪贴板所有权**：历史上有个 bug 用 `md5(bmp)` 去比较 `md5(png)`，两者永远不等，导致桥接每轮循环都重新 `xclip -i` 抢占一次所有权，属主每 2 秒被换一次，opencode 就会撞上“旧属主刚退出、新属主未就绪”的窗口。现在同一张图只解码一次，重复出现时直接复用上次结果重发布（不会重复转换）。如果日志里 `已转换` 每隔几秒刷一次，说明这段逻辑被改坏了。
   - **不要用桥接改写文件剪贴板**：`text/uri-list` / `x-special/gnome-copied-files` 是 RDP 文件传输的输入，桥接改写（哪怕只是“顺手转成 png”）会让文件粘贴失效。`rdp_bridge.py` 顶部有专门守卫，修改时不要删。
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
