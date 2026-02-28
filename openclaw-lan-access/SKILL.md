# Skill: OpenClaw 局域网与 HTTP 访问配置

**适用场景**：当需要从局域网内的其他设备（如手机、另一台电脑）通过浏览器访问 OpenClaw 控制台（HTTP 协议）时。

## 1. 核心配置文件修改 (`openclaw.json`)
确保 `gateway` 配置段包含以下关键字段。

*   **允许局域网监听**：`bind` 必须设置为 `"lan"`。
*   **允许不安全验证**：`allowInsecureAuth` 必须为 `true`（允许非 HTTPS 环境登录）。
*   **允许 Host 验证回退**：`dangerouslyAllowHostHeaderOriginFallback` 必须为 `true`（解决通过 IP 访问时的跨域 Origin 校验问题）。

```json
"gateway": {
  "port": 18789,
  "bind": "lan",
  "controlUi": {
    "allowInsecureAuth": true,
    "dangerouslyAllowHostHeaderOriginFallback": true
  }
}
```

## 2. 浏览器端安全绕过 (Chrome/Edge)
由于现代浏览器视“非本地 HTTP 地址”为不安全环境，会禁用设备指纹识别，导致控制台报错：`control ui requires device identity`。

*   **临时访问**：在 URL 后增加 Token 参数：`http://<IP>:18789/?token=<YOUR_TOKEN>`。
*   **永久解除限制**：
    1. 访问 `chrome://flags/#unsafely-treat-insecure-origin-as-secure`。
    2. 添加 `http://<IP>:18789`。
    3. 设置为 **Enabled** 并重启浏览器。

## 3. 设备配对与批准 (Device Pairing)
当新设备首次连接成功后，控制台会显示 `pairing required` 且状态为“离线”。必须在服务端进行手动批准。

*   **查看申请**：`openclaw devices list`
*   **批准申请**：`openclaw devices approve <RequestId>`
*   **刷新页面**：批准后点击控制台的“刷新”或重开页面即可变为“在线”。

## 4. 常见问题排查
*   **服务无法启动**：检查 `gateway.bind` 是否误设为 `0.0.0.0`（在某些版本中，OpenClaw 仅接受 `loopback`, `lan`, `wan` 等预设值）。
*   **依然提示配对**：确认是否误开了多个会话。批准后一定要点页面上的“刷新”按钮。

---

**建议：** 如果长期使用，最稳健的方案是使用 **Tailscale Serve** 开启 HTTPS，可以完美规避上述所有 HTTP 安全限制。命令为：`openclaw config set gateway.tailscale.mode serve`。
