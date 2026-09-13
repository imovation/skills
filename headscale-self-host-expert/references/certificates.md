# HTTPS 证书策略（国内环境）

主流程见 `SKILL.md` §3。本文档解决一个国内部署的高频阻塞：**Let's Encrypt ACME API 不可达**，
以及可自动化的替代签发路径（ZeroSSL），含 NPM 全自动续期集成。

## 1. 先测连通性（别急着试错）

在服务器上直接测 ACME 目录端点：

```bash
for h in acme-v02.api.letsencrypt.org acme.zerossl.com acme.certum.pl; do
  curl -sk -o /dev/null -w "$h => %{http_code} (%{time_total}s)\n" --max-time 10 https://$h/
done
```

实测参考（阿里云广州 ECS）：`acme-v02.api.letsencrypt.org` 全部超时（Cloudflare
172.64/172.65 段不可达，SCAN 整段 Timeout）；`acme.zerossl.com`、`acme.certum.pl` 可达。
**结论：国内服务器优先 ZeroSSL。**

> 注意区分：LE 的失败是**出站被墙**，与 DNS、证书本身无关；`curl` 超时是典型特征。

## 2. ZeroSSL：免网页注册的 EAB（关键）

ZeroSSL 的 ACME 需要 EAB（external account binding），常规流程要求登录
`app.zerossl.com` 网页获取——该网页在国内多数网络不可达。替代方案：**用邮箱调 REST API
直接换 EAB 凭据，全程无需网页**（服务器可直连 `api.zerossl.com`）：

```bash
curl -s --max-time 15 -X POST https://api.zerossl.com/acme/eab-credentials-email \
  -H 'Content-Type: application/json' \
  -d '{"email":"<你的邮箱>"}'
# 返回：
# {"success":true,"eab_kid":"XXXX","eab_hmac_key":"YYYY"}
```

拿到 `eab_kid` / `eab_hmac_key` 后即可注册 ACME 账户（下面按 NPM 集成说明）。

> 该接口不校验邮箱真实性（无需邮件确认），EAB 凭据与该邮箱账户绑定。
> 每调用一次会注册/复用 ZeroSSL 账户并返回凭据，凭据可长期用于同一服务器。

## 3. NPM 全自动集成（推荐路径）

NPM 内置签发器只支持 `letsencrypt` provider，但支持用 `LE_SERVER` 环境变量覆盖 ACME 服务器：

### 3.1 compose 环境变量

```yaml
environment:
  - LE_SERVER=https://acme.zerossl.com/v2/DV90
```

### 3.2 预注册 EAB 账户（一次性）

NPM 的 certbot 调用不传 EAB 参数，所以在**创建证书前**，先进容器用 certbot 手工注册账户
（账户落盘后，后续 certonly 自动复用，无需再传 EAB）：

```bash
docker exec npm certbot register -n --agree-tos --no-eff-email \
  -m <你的邮箱> \
  --server https://acme.zerossl.com/v2/DV90 \
  --eab-kid '<EAB_KID>' --eab-hmac-key '<EAB_HMAC_KEY>'
# 输出 Account registered. 即成功
```

### 3.3 通过 NPM 正常创建证书

之后走 NPM UI（SSL Certificates → Add Let's Encrypt Certificate）或 API 均可：

```bash
curl -s -X POST http://127.0.0.1:81/api/nginx/certificates \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"provider":"letsencrypt","domain_names":["<域名>"],
       "meta":{"dns_challenge":false}}'
```

> 字段名是 `domain_names`（复数）；meta 只允许 `dns_challenge`（多写字段会 400）。
> 证书签发走 HTTP-01：NPM 已内置 `/.well-known/acme-challenge/` webroot 配置，80 端口需公网可达。
> 续期由 NPM 定时任务自动完成（`/etc/letsencrypt/renewal/npm-<id>.conf` 里 server 已指向 ZeroSSL）。

## 4. 其他 CA 的尝试记录

| CA | 结果 | 说明 |
|----|------|------|
| Let's Encrypt | ❌ 国内出站被墙 | 除非走代理，不可用 |
| ZeroSSL | ✅ 推荐 | 邮箱 API 换 EAB，NPM 集成后可全自动续期 |
| Certum（acme.certum.pl） | ⚠️ 可达但不可用 | 同样要求 EAB，但 NPM certbot 不传 EAB，报 `Server requires external account binding`；需手动 acme.sh 才能用 |
| Buypass / Google GTS | ❌ 端点超时 | — |

## 5. 验证与排障

```bash
# 已签发证书（服务器侧）
docker exec npm cat /etc/letsencrypt/renewal/npm-<id>.conf | grep server

# 外部验证证书链（本机/跳板机执行）
openssl s_client -connect <域名>:443 -servername <域名 </dev/null 2>/dev/null | grep -E 's:|i:'
curl -s https://<域名>/health    # 服务正常性

# 续期排障
docker logs npm 2>&1 | grep -iE 'renew|letsencrypt|certbot' | tail
```

常见错误：

| 报错 | 原因 | 修复 |
|------|------|------|
| `requests.exceptions.ReadTimeout ... acme-v02.api.letsencrypt.org` | LE 被墙 | 切 ZeroSSL（本文档） |
| `Server requires external account binding` | 目标 CA 需 EAB 而 NPM 不传 | 先 `certbot register` 预注册（§3.2） |
| 证书创建 API 400 `data must NOT have additional properties` | 字段名/字段集错误 | `domain_names` 复数；meta 只留 `dns_challenge` |
| 服务器本地 curl 报 `unable to get local issuer certificate` | 容器/系统 CA 库问题 | 外部 `openssl s_client` 验证即可，属正常 |
