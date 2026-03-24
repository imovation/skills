import subprocess
import os
import sys

def run(cmd, sudo=False):
    if sudo:
        cmd = f"sudo {cmd}"
    return subprocess.run(cmd, shell=True, capture_output=True, text=True)

def check_package(pkg):
    return run(f"dpkg -l | grep {pkg}").returncode == 0

def check_os():
    with open("/etc/os-release", "r") as f:
        content = f.read()
        if "Ubuntu 24.04" not in content and "noble" not in content:
            print("❌ 错误：rdp-manager 仅支持 Ubuntu 24.04 (Noble Numbat)。")
            sys.exit(1)
    print("✅ 操作系统检查通过：Ubuntu 24.04")

def auto_fix():
    # 1. 基础依赖检查
    essential_pkgs = ["xclip", "python3", "openssl", "psmisc", "ufw"]
    missing_pkgs = [pkg for pkg in essential_pkgs if not check_package(pkg)]
    
    if missing_pkgs:
        print(f"检测到缺失依赖：{', '.join(missing_pkgs)}，正在尝试自动修复...")
        run("apt update", sudo=True)
        for pkg in missing_pkgs:
            run(f"apt install {pkg} -y", sudo=True)
    
    # 2. 组权限检查 (xrdp 必需)
    user = os.getenv("USER")
    groups = run(f"groups {user}").stdout
    if "ssl-cert" not in groups:
        print(f"正在将用户 {user} 加入 ssl-cert 组以授权 xrdp 访问证书...")
        run(f"usermod -aG ssl-cert {user}", sudo=True)
    
    # 3. 防火墙检查 (3389 端口)
    ufw_status = run("ufw status", sudo=True).stdout
    if "Status: active" in ufw_status and "3389" not in ufw_status:
        print("检测到防火墙已开启但未放行 3389 端口，正在自动配置...")
        run("ufw allow 3389/tcp", sudo=True)
        run("ufw reload", sudo=True)
    
    print("✅ 依赖、权限及防火墙检查全部通过。")

if __name__ == "__main__":
    check_os()
    auto_fix()
