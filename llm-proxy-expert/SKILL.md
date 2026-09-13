---
name: llm-proxy-expert
description: 专门用于诊断和修复中国大陆机房服务器（尤其阿里云/腾讯云等）上 pi、opencode 等 AI coding agent 调用大模型响应慢、请求超时、断连、无法连接模型的问题。当用户反馈"服务器上 pi/opencode 很慢/请求超时/模型不回复/socket 断开/Provider response headers timed out/连不上 opencode.ai"，或需要在国内云服务器上给 LLM agent 部署本地代理（mihomo/clash）、配置 HTTP(S)_PROXY 环境变量、同步机场订阅时，务必使用此 Skill。涵盖从根因判定（GFW 阻断 vs DNS/IPv6 vs 网关本身 vs 余额）→ 服务器本地代理部署 → 环境变量接入 agent → 订阅自动更新的完整工作流，并适配 nvm/node 环境与阿里云元数据特性。
---

# 中国服务器 LLM 代理专家 (China LLM Proxy Expert)

让国内机房 Linux 服务器上的 pi / opencode 能稳定、快速调用境外大模型网关。核心思路：**先定位到底是不是出网被阻断，再确认根因类型，最后对症修复**，而不是盲目换节点、加超时或重装。

本文件是主流程；详细诊断与错误对照见 `references/troubleshooting.md`，订阅自动更新见 `references/subscription-sync.md`，systemd 单元与代理环境变量模板见 `assets/`。

## 0. 先建立关键认知

- pi 与 opencode 常见的付费网关是 opencode-go，真实端点固定在 `https://opencode.ai/zen/go/v1`。**Agent 配置根本不需要动**——慢/超时几乎总是网络出网问题，不是配置问题。
- 阿里云等国内机房直连境外网关的典型表现：opencode 日志 `Provider response headers timed out after 300000ms` / `The socket connection was closed unexpectedly`；curl 直连 `code=000` 且 `time_connect` 卡满超时（TCP 握手无法建立）或 TLS 握手被 reset。
- **诊断金标准**：在一台网络正常的机器上（通常是用户本机 + 本地 clash）经代理 `curl https://opencode.ai` 秒通，而服务器直连超时 → 100% 确诊为服务器出网被阻断。此时唯一解是给服务器配置代理（本技能主路径）或改用国内可达的模型源。

## 1. 诊断流程（先定位根因再动手）

### 1.1 登录并确认环境（nvm 场景）
服务器上的 pi/opencode 常装在 nvm 下，非交互 shell 找不到 PATH，不要因此误判"没装"：
```bash
export NVM_DIR="$HOME/.nvm"; . $NVM_DIR/nvm.sh >/dev/null 2>&1
which pi opencode node npm && pi --version && opencode --version
```

### 1.2 读真实错误日志（不是猜）
```bash
grep -ohiE "(error|timeout|disconnect|timed out)[^\"]*" ~/.local/share/opencode/log/opencode.log | sort | uniq -c | sort -rn | head
# pi 会话日志：ls -t ~/.pi/agent/sessions/*/*.jsonl | head -1（jsonl 里取 stopReason=error 的 message）
```

### 1.3 确认 agent 实际请求的端点
不猜端点，直接读配置里的真实 baseUrl：
```bash
python3 -c "import json;d=json.load(open('/root/.pi/agent/models-store.json'));print([p for p in d if 'opencode-go' in p])"
python3 -c "import json;d=json.load(open('/root/.local/share/opencode/auth.json'));print(list(d.keys()))"
```
opencode-go → `https://opencode.ai/zen/go/v1`。

### 1.4 服务器连通性矩阵
```bash
# -4 强制 IPv4；国内机器常无全局 IPv6，DNS 若只回 AAAA 会卡在 connect（易误判为被墙）
for u in https://opencode.ai https://api.anthropic.com https://generativelanguage.googleapis.com https://models.dev; do
  timeout 15 curl -4 -sS -o /dev/null -m 12 -w "$u => %{http_code} dns=%{time_namelookup}s tls=%{time_appconnect}s total=%{time_total}s\n" "$u"
done
# TCP 层直测（绕过 HTTP 栈干扰）：
timeout 8 bash -c "cat < /dev/null > /dev/tcp/opencode.ai/443" && echo TCP-OK || echo TCP-FAIL
```
判读：
- `code=000 && connect≈满超时` 且 TCP-FAIL → 出网被阻断（GFW SNI/IP 策略或云商限制），多数海外目标全挂、国内目标（models.dev 不一定！它也走海外）参照需谨慎 → 只需确认关键端点挂即可。
- ping ICMP 通、TCP 不通 → 是 TCP/TLS 层阻断，不是路由问题。
- 全部海外 HTTPS 通但个别超时 → 可能只是该站点被 SNI 阻断，仍需要代理。

### 1.5 确认云服务器地域（阿里云元数据）
```bash
curl -s http://100.100.100.200/latest/meta-data/region-id   # 如 cn-guangzhou
```

### 1.6 本地对照基准
```bash
# 若本机有 clash（端口 7897 等）
curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 12 -w "%{http_code} %{time_total}s\n" https://opencode.ai
```
本机走代理秒通 + 服务器不通 → 定案，进入 §2。

## 2. 修复：给服务器部署本地代理（mihomo）

只绑 `127.0.0.1`，不对外开放；用用户已有的机场订阅。前提：**机场节点从国内服务器 TCP 可达**（多数大陆机场可达，测一下再动手）：
```bash
timeout 8 bash -c "cat < /dev/null > /dev/tcp/212.74.7.29/13018" && echo node-OK
```

### 2.1 准备二进制与 geo 库
- 二进制：直接 scp 本机 clash-verge 自带的 `verge-mihomo`（/usr/bin 下，静态编译，与本地订阅天生兼容），或从 GitHub Releases 下载 `mihomo linux-amd64`（国内服务器访问 GitHub 通常可达）。
- geo 库：`Country.mmdb`、`geoip.dat`、`geosite.dat`（GEOIP 规则必需），同样从本机 clash 数据目录同步。

### 2.2 生成服务器配置（关键：不落盘明文 Token）
配置**必须从本机已有订阅派生**，不要在技能/脚本里写死机场链接或 Token：
1. 在本机找订阅配置文件：`~/.local/share/io.github.clash-verge-rev.clash-verge-rev/profiles/<uid>.yaml`（最活跃的 remote profile）。
2. 下载后做**归一化改写**（用正则/python，别只 sed 一行，避免改不完）：
   ```python
   mixed-port -> 7897
   external-controller -> '127.0.0.1:9090'
   secret -> 随机串（管理 API 用，只走本地）
   dns.listen -> '127.0.0.1:53'
   ```
   其余 proxies/proxy-groups/rules/dns 保持原样。
3. 上传 `config.yaml`（`chmod 600`）+ geo 库到 `/etc/mihomo/`，二进制到 `/usr/local/bin/mihomo`。

### 2.3 systemd 托管
用 `assets/mihomo.service` 模板，`systemctl enable --now mihomo`，确认监听：
```bash
ss -tlnp | grep -E "7897|9090"
```

### 2.4 部署后验证（先过关再接 agent）
```bash
curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 20 -w "%{http_code}\n" https://opencode.ai   # 期望 200
```

## 3. 让 pi / opencode 走代理（环境变量接入）

pi 的 HTTP 栈（undici EnvHttpProxyAgent）与 opencode 均读 `HTTP_PROXY/HTTPS_PROXY/NO_PROXY`（**不读 ALL_PROXY**）。三处写入：

1. `/etc/profile.d/proxy.sh`（交互 shell 与 login）——用 `assets/proxy-env.sh` 模板，**NO_PROXY 必须包含阿里云元数据 `100.100.100.200` 及内网段**，避免自家内部服务被代理吞掉。
2. `/etc/environment`（systemd 服务；**不能带 `export` 关键字**）。
3. `~/.bashrc`：`source /etc/profile.d/proxy.sh`（非托管、用户手动 ssh 会话的场景）。

改完先确认非交互会话也能拿到变量：`ssh root@host 'echo $HTTPS_PROXY'`。

## 4. 订阅自动更新（机场轮换节点是常态）

机场节点端口/线路会不定期轮换，**必须做自动刷新**，否则几周后整条链路悄悄失效。关键坑：机场 API 站点经常对云厂商 IP（阿里云等）做 TLS 阻断，**从服务器拉订阅拉不下来，但从用户本机可以**。因此正确做法是"本机拉取 → 推送到服务器 → 服务器应用新节点"，且**优先用 provider 文件解耦 + 热重载**（每天只替换节点文件、调 API 热重载，不重启、不覆写监听/secret 配置），简单路径为兜底。完整方案见 `references/subscription-sync.md`；本机侧脚本 `scripts/sync-mihomo-provider.sh`（简单路径用 `scripts/sync-mihomo.sh`），服务器侧脚本 `scripts/apply-provider.sh`。订阅 Token 一律存本机 `~/.config/mihomo-sync/sub-url`（chmod 600）运行时读取，控制器 secret 只存服务器 `/etc/mihomo/.controller_secret`，凭据不出服务器。

## 5. 终验（模拟用户真实使用，全新会话）

```bash
source /etc/profile.d/proxy.sh
opencode run --auto "只输出两个字：正常"     # 期望有正常回复
pi -p -nt "只回答四个字：连接成功"
```
同时 `journalctl -u mihomo -n 5` 能看到 `--> opencode.ai:443 match ... using <节点>` 即符合预期。

## 6. 兜底与其它方案

- **不想占机场多设备名额 / 本机长期在线**：用 SSH 反向隧道把本机 clash 暴露到服务器
  `ssh -R 127.0.0.1:17897:127.0.0.1:7897 root@server`，然后代理变量指到 `127.0.0.1:17897`。缺点：依赖本机开机与隧道存活，适合临时应急。
- **完全绕开境外网关**：改用国内可达的模型 API（官方 DeepSeek/Kimi/通义等），改 `settings.json`/`auth.json` 即可绕过代理依赖，但用户已有的 opencode-go 充值与模型生态会作废，与用户确认后再切换。

## 常见坑汇总

- SSH host key changed（服务器重装过）→ `ssh-keygen -R <ip>` 再 `StrictHostKeyChecking=accept-new`。
- 服务器无全局 IPv6，DNS 只回 AAAA 时 curl 卡 connect——用 `-4` 再测一次区分"被墙"与"无 IPv6"。
- 非交互 shell 找不到 nvm 里的命令 → 先 source nvm.sh 再 `which`。
- 配置里不要写死 token，参考 pi-expert 的安全红线：涉及认证一律"从配置文件运行时读取"。
- 代理要绑定 127.0.0.1，别开 `allow-lan`，不要在云安全组放行 7897。