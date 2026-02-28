---
name: wsl-opencode-image-paste
description: Fix opencode image paste in WSL. Use when user cannot paste images in opencode TUI running on WSL.
---

# WSL Opencode Image Paste Fix

## Problem
在 WSL 环境下使用 opencode TUI 时，无法通过 Ctrl+V 粘贴图片。

## Root Cause
Windows Terminal 默认拦截了 Ctrl+V 快捷键，阻止转发到 WSL 中的 opencode。

## Solution

执行以下命令创建配置文件：

```bash
mkdir -p ~/.config/opencode
cat > ~/.config/opencode/opencode.json << 'EOF'
{
  "keybinds": {
    "input_paste": "alt+v"
  }
}
EOF
```

## 告诉用户
重新启动 opencode，然后使用 **Alt+V** 粘贴图片。

## Note
这是最稳定的方案。Alt+V 虽然需要适应，但不会影响 Windows Terminal 的其他功能。
