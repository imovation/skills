# WSL2 镜像模式 Ollama 极致配置指南 (Skill)

当你在 WSL2 环境下使用 `networkingMode=mirrored`（镜像模式）运行 Ollama，且希望将模型存储在 D 盘时，请调用此 Skill。

## 核心要求
- **系统环境**：WSL2 (Ubuntu/Debian)
- **宿主机**：Windows 11 (镜像模式推荐版本)
- **运行方式**：Ollama 需作为 systemd 服务运行

## 🛠️ 标准配置流程

### 1. 优化 Windows `.wslconfig` 配置
确保 `C:\Users\<你的用户名>\.wslconfig` 包含以下关键项，解决 DNS 解析和代理同步问题：
```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true        # 必选：由 Windows 代谢 DNS，解决 TLS 握手超时
autoProxy=true           # 必选：自动同步 Windows 代理设置
hostAddressLoopback=true # 可选：增强 localhost 回环性能
```
*注意：修改后需在 PowerShell 执行 `wsl --shutdown` 重启生效。*

### 2. 模型存储迁移（保卫 C 盘）
将模型存储路径指向 Windows D 盘挂载点。
```bash
# 创建并授权目录
sudo mkdir -p /mnt/d/ollama_models
sudo chown -R $USER:$USER /mnt/d/ollama_models
```

### 3. Systemd 服务环境变量注入
直接修改 `/etc/systemd/system/ollama.service`，注入存储路径和代理（默认 Clash 端口 `7897`）。

**自动化命令模板：**
```bash
# 设置变量（根据实际情况修改）
MODEL_PATH="/mnt/d/ollama_models"
PROXY_PORT="7897"

# 注入配置到服务文件
sudo sed -i "/\[Service\]/a Environment=\"OLLAMA_MODELS=$MODEL_PATH\"" /etc/systemd/system/ollama.service
sudo sed -i "/\[Service\]/a Environment=\"HTTP_PROXY=http://127.0.0.1:$PROXY_PORT\"" /etc/systemd/system/ollama.service
sudo sed -i "/\[Service\]/a Environment=\"HTTPS_PROXY=http://127.0.0.1:$PROXY_PORT\"" /etc/systemd/system/ollama.service

# 重载并重启服务
sudo systemctl daemon-reload
sudo systemctl restart ollama
```

### 4. 结果验证
执行以下命令确保配置生效：
1. `systemctl show ollama --property=Environment` (检查代理和路径变量)
2. `ollama pull tinyllama` (检查网络连通性)
3. `ls -lh /mnt/d/ollama_models/blobs` (确认数据写入 D 盘)

## ⚠️ 常见故障排查
- **TLS 握手超时 (TLS handshake timeout)**：通常是缺少 `dnsTunneling=true` 或代理端口不匹配。
- **D 盘权限不足**：确保目录已执行 `chown` 授权。
- **.wslconfig 报错“键未知”**：检查文件编码是否为 UTF-8（无 BOM），且无隐藏乱码。
