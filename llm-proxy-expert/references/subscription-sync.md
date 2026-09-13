# 订阅自动更新方案（本机拉取 → 推送服务器）

机场（如速鹰）的节点端口/线路会不定期轮换，静态配置几周后就会失效。而机场订阅 API 站点经常对**云厂商 IP**（阿里云等）做 TLS 阻断（实测 `SSL_ERROR_SYSCALL` / `Connection reset`，直连与走代理都失败），但从用户本机可正常拉取。因此**绝不能"服务器自己定时拉订阅"**，正确路径是：**本机拉 → 推送到服务器 → 让 mihomo 用上新节点 → 验证**。

## 两种落地架构（推荐热重载，简单路径兜底）

| | 简单路径（整配置同步 + 重启） | **推荐路径（provider 解耦 + API 热重载）** |
|---|---|---|
| 每天改什么 | 整个 `config.yaml` | 只有一个 provider 节点文件 |
| 服务器配置 | 每次都要做归一化改写，防订阅覆写监听/secret | **配置结构固定，永远不会被订阅覆写**（订阅只进 provider 文件） |
| 生效方式 | `systemctl restart mihomo`（会**短暂掐断**正在用的代理连接） | 调 external-controller API `PUT /providers/proxies/airport` **热重载，不断连接** |
| 出错回滚 | 靠前一版配置备份人工处理 | 校验→原子替换→重载→失败自动回滚，全程脚本化 |
| 适用场景 | 节点数量少、配置长期稳定 | 机场轮换频繁、要求持续在线不抖动的标配 |
| 脚本 | `scripts/sync-mihomo.sh` | `scripts/sync-mihomo-provider.sh`（本机）+ `apply-provider.sh`（服务器） |

默认按**推荐路径**实施；若现场设备/时间不允许做一次性 provider 迁移，沿用简单路径亦可，但必须保留"每次归一化 + 重启后验证"两条安全底线。

---

## 推荐路径：provider 解耦 + 热重载

```
本机 cron → 拉订阅(经本机 clash) → 转 provider 格式 → scp 到 staging → ssh 触发服务器 apply-provider.sh
        → 服务器：校验节点数 → 备份 → 原子替换 → API 热重载 → 走代理验证 opencode.ai==200（失败自动回滚）
```

### 前置条件（两条路径通用）

1. **专门生成一把 SSH 免密密钥**（避免把密码写进 cron）：
   ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519_sync -C "mihomo-sync"
   ssh-copy-id -i ~/.ssh/id_ed25519_sync.pub root@<server>
   ```
2. 订阅链接（含 Token）**单独存文件、chmod 600**，脚本运行时读取，绝不写进本技能或脚本明文：
   ```bash
   mkdir -p ~/.config/mihomo-sync && chmod 700 ~/.config/mihomo-sync
   echo '<订阅URL>' > ~/.config/mihomo-sync/sub-url && chmod 600 ~/.config/mihomo-sync/sub-url
   ```
3. 服务器已按 SKILL.md §2 完成初始部署（`mixed-port 7897`、`external-controller 127.0.0.1:9090`、`secret` 已就位）。

### 一次性迁移（把服务器配置改成 provider 引用）

1. 把当前订阅里的节点拆出来作为首个 provider 文件：
   ```bash
   ssh root@<server> 'mkdir -p /etc/mihomo/providers/.bak'
   # 从现有 config.yaml 抽 proxies 段存为 /etc/mihomo/providers/airport.yaml（chmod 644）
   ```
2. 主配置 `config.yaml` 收敛为"声明 + 组引用"（删除内联 `proxies:`）：
   ```yaml
   proxy-providers:
     airport:
       type: file
       path: ./providers/airport.yaml
       health-check: { enable: true, url: https://www.gstatic.com/generate_204, interval: 300 }

   proxy-groups:
     - name: PROXY
       type: url-test
       use: [airport]
       url: https://www.gstatic.com/generate_204
       interval: 300
       tolerance: 50
   ```
   `rules:` 仍指向 `PROXY` 组，不动。
3. controller secret 抽出到服务器本机受保护文件（**凭据不出服务器**）：
   ```bash
   ssh root@<server> 'grep -E "^secret:" /etc/mihomo/config.yaml | awk "{print \$2}" | tr -d "\x27\x22" > /etc/mihomo/.controller_secret && chmod 600 /etc/mihomo/.controller_secret'
   ```
4. 上传并安装 `apply-provider.sh`（见 scripts/）到服务器 `/usr/local/bin/apply-provider.sh`（root 可执行）。
5. **收窄推送密钥权限**：在服务器 `~/.ssh/authorized_keys` 中给 `id_ed25519_sync` 条目前缀 forced-command，让它只能干一件事，本机即使被入侵也无法用它跑任意命令：
   ```
   command="/usr/local/bin/apply-provider.sh",no-agent-forwarding,no-port-forwarding,no-pty,no-X11-forwarding ssh-ed25519 AAAA... mihomo-sync@local
   ```
   注意：forced-command 后该密钥只能执行 `apply-provider.sh <file>` 一个操作，验证/回滚都封装在脚本内。
6. `systemctl restart mihomo` 一次完成迁移，验证 `opencode.ai` 走代理 200。

### 本机脚本 `scripts/sync-mihomo-provider.sh`

要点（全部绝对路径，适配 cron 极简 PATH）：
- 经本机 clash 拉订阅（失败直连兜底）→ 用 python 只取顶层 `proxies` 段写成 provider 文件（统一格式，服务器零转换逻辑）。
- 本地校验节点数下限（防机场返回报错页/空订阅覆盖好配置），失败即退出、绝不推送。
- scp 到服务器 staging（**不直接覆盖线上文件**）→ `ssh` 触发 forced-command 的 `apply-provider.sh <staging>`。
- 服务器端脚本负责：再校验 → 备份 → 原子替换 → API 热重载 → 走代理验证 `opencode.ai==200` → **任一环失败自动回滚**并把退出码带回来，便于 cron 告警。

### 服务器脚本 `scripts/apply-provider.sh`（运行在服务器）

```bash
#!/bin/bash
set -euo pipefail
STAGE="${1:?usage: apply-provider.sh <staged-file>}"
PROVIDER_DIR="/etc/mihomo/providers"; NAME=airport
LIVE="$PROVIDER_DIR/$NAME.yaml"; BAK_DIR="$PROVIDER_DIR/.bak"
SECRET_FILE="/etc/mihomo/.controller_secret"; CTRL="127.0.0.1:9090"

[ -s "$STAGE" ] || { echo "empty staging"; exit 2; }
NODES="$(python3 - "$STAGE" <<'PY'
import sys, yaml
print(len((yaml.safe_load(open(sys.argv[1])) or {}).get("proxies") or []))
PY
)"
[ "${NODES:-0}" -ge 3 ] || { echo "too few nodes=$NODES"; exit 3; }

mkdir -p "$BAK_DIR"
[ -f "$LIVE" ] && cp -a "$LIVE" "$BAK_DIR/$NAME.yaml.$(date +%Y%m%dT%H%M%S)"
install -m 0644 "$STAGE" "$LIVE"
SECRET="$(cat "$SECRET_FILE")"

reload() { curl -s -o /dev/null -w '%{http_code}' -X PUT "http://$CTRL/providers/proxies/$NAME" \
  -H "Authorization: Bearer $SECRET"; }

CODE="$(reload)"
if [ "$CODE" != "200" ] && [ "$CODE" != "204" ]; then
  echo "reload failed ($CODE), rolling back"; LATEST="$(ls -1t "$BAK_DIR/$NAME.yaml."* 2>/dev/null | head -1)"
  [ -n "$LATEST" ] && { install -m 0644 "$LATEST" "$LIVE"; reload >/dev/null || true; }
  exit 4
fi

CODE="$(curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 20 -w '%{http_code}' https://opencode.ai)"
[ "$CODE" = "200" ] || { echo "egress verify failed ($CODE), rolling back"; LATEST="$(ls -1t "$BAK_DIR/$NAME.yaml."* 2>/dev/null | head -1)"; # 回滚同上
  exit 5; }
echo "provider $NAME applied, opencode.ai=200"
```
（完整版见 `scripts/apply-provider.sh`。）

## 简单路径（整配置同步 + 重启，兜底）

原文保留：`scripts/sync-mihomo.sh` 拉订阅 → **归一化改写（每回必刷新下面 4 键，订阅会覆写回机场默认值）**：
```python
mixed-port -> 7897
external-controller -> '127.0.0.1:9090'
secret -> <同部署时的一致随机串>
dns.listen -> '127.0.0.1:53'
```
→ scp 覆盖 `config.yaml` → `systemctl restart mihomo` → `curl -x … https://opencode.ai` 期望 200。重启会短暂断开在用代理连接。

## cron 落地

```bash
crontab -l > /tmp/ct; echo "17 4 * * * /home/<user>/.local/bin/sync-mihomo-provider.sh >> /home/<user>/.local/var/sync-mihomo.log 2>&1" >> /tmp/ct; crontab /tmp/ct
```
- 选凌晨低峰（04:00-05:00）；推荐路径热重载不断连，简单路径重启会短暂断。
- 本机 cron 依赖本机开机；家庭电脑突发关机漏更无碍（配置仍可用只是节点不刷新），下个开机日自然补上。

## 状态核对

```bash
tail -3 ~/.local/var/sync-mihomo.log
ssh root@<server> "systemctl is-active mihomo"
ssh root@<server> "curl -sS -x http://127.0.0.1:7897 -o /dev/null -m 20 -w '%{http_code}\n' https://opencode.ai"
# 推荐路径还可看 provider 是否加载：
ssh root@<server> "curl -s -H \"Authorization: Bearer \$(cat /etc/mihomo/.controller_secret)\" http://127.0.0.1:9090/providers/proxies/airport | head -c 200"
```

## 失败模式（推荐路径脚本已内置防御）

| 场景 | 处理 |
|---|---|
| 本机拉取失败 / 机场 502 | 脚本非零退出，**不推送**，线上配置保持不动 |
| 空中订阅 / HTML 报错页 | 节点数下限拦截（本机 + 服务器双重） |
| XML/传输中断 | 只写 staging，原子 `mv` 前不触碰线上文件 |
| 热重载 API 非 2xx | 自动回滚最近备份并重载 |
| 更新后出口不通（opencode.ai≈200 失败） | 自动回滚上一版并重载 |
| mihomo 未启动 | API/curl 失败 → 回滚 → 记录，由既有进程守护拉起 |

## 其它注意

- 订阅在服务器上会多占用一个设备名额：大陆机场通常限 3~5 台并发，与用户确认额度后再长期挂机。
- 若机场提供备用/镜像订阅域名且不被云 IP 阻断，也可直接配服务器上 mihomo 内置 `proxy-provider type: http + interval`，此时不需要本机 cron，但订阅 URL 仍应写进服务器上权限 600 文件、从配置引用，不落盘明文到技能。
- 涉及 Token 的文件（`sub-url`）与密钥（`id_ed25519_sync`）都要 `chmod 600`；controller secret 只存服务器 `/etc/mihomo/.controller_secret`（600/root），本机脚本永远不持有。
- 备份目录 `providers/.bak/` 会天天增长，cron 里加一句清理（保留最近 7 份）。