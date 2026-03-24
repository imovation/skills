import subprocess
import os

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

# 1. 环境自检与修复 (Self-healing)
print("正在检查系统环境与依赖...")
self_check_path = os.path.join(os.path.dirname(__file__), "self_check.py")
check_result = run(f"python3 {self_check_path}")
if check_result.returncode != 0:
    print(check_result.stdout)
    sys.exit(1)

# 2. 正常业务逻辑
print("正在停止 xrdp 服务并清理端口...")
run("sudo systemctl stop xrdp xrdp-sesman")
run("sudo systemctl disable xrdp xrdp-sesman")
run("sudo fuser -k 3389/tcp")

print("正在开启内置远程登录 (gnome-remote-desktop)...")
run("sudo systemctl enable gnome-remote-desktop")
run("sudo systemctl restart gnome-remote-desktop")

# 检查证书
cert_path = "/var/lib/gnome-remote-desktop/.local/share/gnome-remote-desktop/certificates/rdp-tls.crt"
if not os.path.exists(cert_path):
    print("证书缺失，正在生成...")
    run(f"sudo openssl req -x509 -newkey rsa:4096 -keyout {cert_path.replace('.crt', '.key')} -out {cert_path} -days 3650 -nodes -subj '/CN=Ubuntu-RDP'")
    run(f"sudo chown gnome-remote-desktop:gnome-remote-desktop {os.path.dirname(cert_path)}/rdp-tls.*")
    run(f"sudo chmod 600 {os.path.dirname(cert_path)}/rdp-tls.*")

print("正在重启剪贴板桥接 (内化版)...")
run("pkill -f rdp_bridge.py")
bridge_path = os.path.join(os.path.dirname(__file__), "rdp_bridge.py")
subprocess.Popen(["python3", bridge_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("\n" + "="*50)
print("🚀 切换至【内置 RDP】完成！")
print("="*50)
print("1. [必做] 开启服务：设置 -> 系统 -> 远程登录 -> 开启开关。")
print("2. [必做] 设置凭据：点击铅笔图标自定义用户名和密码。")
print("3. [必做] 物理机注销：点击注销 (Log Out)。")
print("4. [Windows 连接]：输入新设凭据，接受证书。")
print("="*50)
