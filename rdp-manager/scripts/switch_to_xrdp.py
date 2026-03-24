import subprocess
import os
import time
import sys

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

print("\n" + "🚀 正在启动【极致流程版】RDP 切换程序..." + "\n")

# --- 阶段 1: 不会导致黑屏的后台任务 ---
print("[1/5] 🔍 正在进行系统环境自检与依赖修复...")
self_check_path = os.path.join(os.path.dirname(__file__), "self_check.py")
run(f"python3 {self_check_path}")

print("[2/5] 🛠️ 正在后台预热 RDP 服务并清理冲突...")
run("sudo systemctl stop gnome-remote-desktop")
run("sudo systemctl disable gnome-remote-desktop")
run("sudo fuser -k 3389/tcp")
run("sudo systemctl enable xrdp xrdp-sesman")
run("sudo systemctl restart xrdp")

print("[3/5] 📦 正在注入 RDP 环境变量补丁...")
xsession_path = os.path.expanduser("~/.xsession")
with open(xsession_path, "w") as f:
    f.write("export GNOME_SHELL_SESSION_MODE=ubuntu\n")
    f.write("export XDG_CURRENT_DESKTOP=Ubuntu:GNOME\n")
    f.write("export XDG_SESSION_TYPE=x11\n")
    f.write("gnome-session\n")

print("[4/5] 正在后台启动剪贴板桥接服务...")
run("pkill -f rdp_bridge.py")
bridge_path = os.path.join(os.path.dirname(__file__), "rdp_bridge.py")
subprocess.Popen(["python3", bridge_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# --- 阶段 2: 关键临界点倒计时 ---
print("\n" + "="*50)
print("✨ 后台准备工作已全部就绪！")
print("⚠️  警告：系统即将在 10 秒后强制注销当前会话以完成接管。")
print("="*50 + "\n")

for i in range(10, 0, -1):
    sys.stdout.write(f"\r⏳ 最后的保存时间: {i} 秒... ")
    sys.stdout.flush()
    time.sleep(1)

print("\n\n[5/5] 🎯 正在执行最终物理会话接管...")

# --- 阶段 3: 导致黑屏的破坏性操作 ---
# 先温和通知
run("sudo pkill -SIGTERM -u $(whoami) gnome-session")
# 极短缓冲
time.sleep(1)
# 最终强杀
run("sudo loginctl terminate-user $(whoami)")

print("\n" + "="*50)
print("✅ 切换至【xrdp (Xorg 模式)】极致版已成功！")
print("="*50)
print("1. [物理机] 现在应该已闪现回登录界面。")
print("2. [Windows 连接] 请确保选择 Xorg 模式。")
print("="*50)
