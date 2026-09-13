# 故障参考：信号、判读与命令详解

本文件是 `SKILL.md` §1/§2 的展开。按"信号 → 含义 → 下一步"组织。全部命令面向中国大陆机房 Linux 服务器（阿里云/腾讯云等），nvm 安装的 agent 需先 `export NVM_DIR="$HOME/.nvm"; . $NVM_DIR/nvm.sh`。

## 一、错误对照表

| 表现/错误文案 | 真实含义 | 下一步 |
|--------------|---------|--------|
| opencode 日志 `Provider response headers timed out after 300000ms` | 请求发出去后 5 分钟收不到响应头，上游链路不通或黑洞 | 诊断矩阵定位是 TCP/TLS 哪层断 |
| opencode 日志 `Cannot connect to API: The socket connection was closed unexpectedly` | TLS 握手/连接中途被 reset（常见 SNI 阻断） | strace / curl 复现，确认目标域名 |
| pi-web 显示 "Unknown provider error" | 兜底文案，任何空错误请求失败都显示它 | 读 pi 会话 jsonl 拿真实 error |
| 300/500/403/429 但能连上 | 网络通，问题在网关/余额/并发 | 检查 opencode-go 余额、模型可用性 |
| `curl` code=000，connect 时间≈超时时长 | TCP 三次握手没完成（出网被断/丢包黑洞） | `/dev/tcp` 直测确认；走代理再测 |
| code=000，但 dns/connect 都是 0 且瞬间失败 | DNS 只回 AAAA、机器无 IPv6 又没试 v4 | 强制 `-4` 重测 |
| TLS 握手瞬间 reset（SSL_ERROR_SYSCALL） | SNI 级阻断，常见于机场订阅站对云 IP | 走本机拉取推送（订阅同步） |

## 二、诊断命令详解

### 1. 读合法日志
```bash
# opencode（最有用，`error=` 字段带原始错误）
grep -ohiE "(error|timeout|disconnect|timed out)[^\"]*" ~/.local/share/opencode/log/opencode.log | sort | uniq -c | sort -rn | head

# pi 会话（按项目分组）
F=$(ls -t ~/.pi/agent/sessions/*/*.jsonl | head -1)
python3 -c "
import json
for line in open('$F'):
    d=json.loads(line)
    if d.get('type')=='message' and d['message'].get('role')=='assistant' and d['message'].get('stopReason')=='error':
        print('ERROR:', repr(d['message'].get('errorMessage'))[:300])
"
```

### 2. 端点信息（不猜）
```bash
python3 - <<'EOF'
import json
try:
    d=json.load(open('/root/.pi/agent/models-store.json'))
    print('pi providers:', list(d.keys()))
    for p in d:
        if 'opencode-go' in p:
            print('baseUrl sample:', p, '=>', d[p]['models'][0].get('baseUrl'))
except Exception as e:
    print('pi models-store:', e)
try:
    d=json.load(open('/root/.local/share/opencode/auth.json'))
    print('opencode providers:', list(d.keys()))
except Exception as e:
    print('opencode auth:', e)
EOF
```

### 3. 连通性矩阵（区分"被墙"与"无 IPv6"）
```bash
for u in https://opencode.ai https://api.anthropic.com https://generativelanguage.googleapis.com https://models.dev; do
  echo "--- $u"
  timeout 15 curl -4 -sS -o /dev/null -m 10 -w "v4: code=%{http_code} connect=%{time_connect}s tls=%{time_appconnect}s total=%{time_total}s\n" "$u" 2>&1 | tail -1
  timeout 15 curl -6 -sS -o /dev/null -m 10 -w "v6: code=%{http_code} connect=%{time_connect}s tls=%{time_appconnect}s total=%{time_total}s\n" "$u" 2>&1 | tail -1
done
ip -6 addr show scope global | grep -c inet6   # 0 = 无全局 IPv6
```
判读：
- v4 成功即网络基本通，v6 失败正常（无 IPv6）。
- v4 也 code=000 且 connect≈10s → TCP 层被断，需代理。
- `models.dev`（Cloudflare）通而 `opencode.ai` 不通 → 是 SNI/IP 级定向阻断，不是整段海外不可达，更坐实"需要代理"。

### 4. TCP 层直测（绕过 HTTP 栈 / DNS 假象）
```bash
timeout 8 bash -c "cat < /dev/null > /dev/tcp/opencode.ai/443" && echo TCP-OK || echo TCP-FAIL
```

### 5. 云地域（仅阿里云）
```bash
curl -s http://100.100.100.200/latest/meta-data/region-id && echo
```

### 6. 本地对照基准（本机 clash）
```bash
curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 12 -w "proxy opencode.ai => %{http_code} %{time_total}s\n" https://opencode.ai
```
本机经代理秒通、服务器直连 code=000，即确诊"服务器出网被阻断"，根因与配置无关。

### 7. 反推机场节点可达性（部署前必测）
```bash
# 从订阅配置取任一节点 server+port 后：
timeout 8 bash -c "cat < /dev/null > /dev/tcp/<node_server>/<node_port>" && echo node-OK || echo node-FAIL
```

## 三、部署 mihomo 服务器的完整命令

```bash
# 服务器建目录
mkdir -p /etc/mihomo /usr/local/bin
chmod 600 /etc/mihomo/config.yaml

# systemd
cat > /etc/systemd/system/mihomo.service <<'EOF'
[Unit]
Description=Mihomo Proxy
After=network-online.target
Wants=network-online.target
[Service]
Type=simple
ExecStart=/usr/local/bin/mihomo -d /etc/mihomo
Restart=on-failure
RestartSec=3
LimitNOFILE=1048576
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable --now mihomo
sleep 3 && systemctl is-active mihomo && ss -tlnp | grep -E "7897|9090"

# 部署验证
curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 20 -w "opencode.ai=%{http_code}\n" https://opencode.ai
```

## 四、接入 agent 的环境变量（三处，缺一不可）

```bash
# 1) /etc/profile.d/proxy.sh —— 交互/login shell
cat > /etc/profile.d/proxy.sh <<'EOF'
export HTTP_PROXY=http://127.0.0.1:7897
export HTTPS_PROXY=http://127.0.0.1:7897
export http_proxy=http://127.0.0.1:7897
export https_proxy=http://127.0.0.1:7897
export NO_PROXY=localhost,127.0.0.1,::1,100.100.100.200,*.aliyun.com,*.aliyuncs.com,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12
export no_proxy=localhost,127.0.0.1,::1,100.100.100.200,*.aliyun.com,*.aliyuncs.com,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12
EOF

# 2) /etc/environment —— systemd 服务；不带 export
# 3) ~/.bashrc —— 追加 source /etc/profile.d/proxy.sh
```
验证 systemd 场景：`systemctl restart <svc>; tr '\0' '\n' < /proc/<PID>/environ | grep -i proxy`。
验证 ssh 场景：`sshpass -e ssh root@host 'echo $HTTPS_PROXY'`。

## 五、验证 Agent 冒烟（全新会话，别复用 bandaid）

```bash
opencode run --auto "只输出两个字：正常"        # 期望出现模型回复
pi -p -nt "只回答四个字：连接成功"              # 期望输出"连接成功"
journalctl -u mihomo -n 5 --no-pager            # 应出现 --> opencode.ai:443 match Match using <节点>
```