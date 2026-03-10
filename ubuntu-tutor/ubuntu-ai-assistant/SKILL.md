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

### 1.2 路径管理与工作空间 (新手必看)
在 OpenCode 中工作时，建议始终处于项目根目录下。

### 1.3 RDP 剪贴板与图片粘贴 (正式解决方案)
在 Ubuntu 24.04 的 RDP (GNOME Remote Desktop) 环境下，直接粘贴截图可能失效。

#### 1.3.1 核心修复脚本
如果粘贴失效，请执行以下指令重建并启动修复桥接器：


### 重建文件: rdp-clipboard-bridge.py
 ```bash
 mkdir -p /home/imovation/agent-skill-factory/projects/ubuntu-ai-assistant/assets
 cat <<'EOF' > /home/imovation/agent-skill-factory/projects/ubuntu-ai-assistant/assets/rdp-clipboard-bridge.py
import subprocess
import os
import time
import hashlib
import urllib.parse

# 针对 RDP 环境设置显示端口
os.environ['DISPLAY'] = ':1'

def get_clipboard_data(target):
    try:
        return subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', target, '-o'], 
                                     stderr=subprocess.DEVNULL)
    except:
        return None

def set_clipboard_data(target, data):
    try:
        subprocess.run(['xclip', '-selection', 'clipboard', '-t', target, '-i'], input=data, check=True)
        return True
    except:
        return False

last_hash = ""

while True:
    try:
        # 探测当前剪贴板支持的格式
        targets = subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', 'TARGETS', '-o'], 
                                        stderr=subprocess.DEVNULL).decode('utf-8').splitlines()
        
        # 场景 A: 发现图片数据 (截图)
        if 'image/png' in targets:
            raw_data = get_clipboard_data('image/png')
            if raw_data:
                current_hash = hashlib.md5(raw_data).hexdigest()
                if current_hash != last_hash:
                    set_clipboard_data('image/png', raw_data)
                    last_hash = current_hash
        
        # 场景 B: 发现文件路径 (复制文件)
        elif 'text/uri-list' in targets:
            uri_data = get_clipboard_data('text/uri-list')
            if uri_data:
                current_hash = hashlib.md5(uri_data).hexdigest()
                if current_hash != last_hash:
                    uri = uri_data.decode('utf-8').strip()
                    if uri.startswith('file://'):
                        path = urllib.parse.unquote(uri[7:])
                        if os.path.exists(path) and path.lower().endswith(('.png', '.jpg', '.jpeg')):
                            with open(path, 'rb') as f:
                                img_data = f.read()
                                mime = 'image/png' if path.lower().endswith('.png') else 'image/jpeg'
                                set_clipboard_data(mime, img_data)
                                last_hash = current_hash
    except:
        pass
    time.sleep(1)
EOF
 ```


#### 1.3.2 配置自启动
确保桥接器开机自动运行：
```bash
mkdir -p ~/.config/autostart
cat <<EOF > ~/.config/autostart/rdp-clipboard-bridge.desktop
[Desktop Entry]
Type=Application
Exec=python3 /home/imovation/agent-skill-factory/projects/ubuntu-ai-assistant/assets/rdp-clipboard-bridge.py
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name=RDP Clipboard Bridge
EOF
```

## 2. AI 开发工具 (OpenCode/OpenClaw)
(后续根据需求进化)
