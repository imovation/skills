# TURN/STUN 服务器（音视频通话）

Synapse 的 `turn_shared_secret` 是时间受限凭证模式，coturn 必须开启
`use-auth-secret` 并配置相同密钥，否则通话会拿到凭证却无法中继。

## 1. 准备 coturn 配置

```bash
SECRET=$(openssl rand -hex 32)   # 记下来，下一步填入 homeserver.yaml
cat > /root/matrix/turnserver.conf << EOF
use-auth-secret
static-auth-secret=${SECRET}
realm=<你的域名>
min-port=49152
max-port=65535
EOF
```

## 2. 启动 coturn

```bash
docker run -d --name coturn \
  --network matrix_default \
  -p 3478:3478 -p 3478:3478/udp \
  -p 5349:5349 -p 5349:5349/udp \
  -v /root/matrix/turnserver.conf:/etc/coturn/turnserver.conf \
  coturn/coturn -c /etc/coturn/turnserver.conf
```

## 3. homeserver.yaml 追加

```yaml
turn_uris:
  - "turn:<你的域名>:3478?transport=udp"
  - "turn:<你的域名>:3478?transport=tcp"
  - "turns:<你的域名>:5349?transport=tcp"
turn_shared_secret: "<与 turnserver.conf 的 static-auth-secret 相同>"
turn_user_lifetime: 86400000
```

## 4. 端口与防火墙

除 3478/5349 外，中继媒体端口范围 `49152-65535/udp` 也要放行（云安全组 +
服务器本机防火墙），否则通话建立后无声音。仅内网通话时无需开放公网 STUN。

## 5. 验证

用 Element 发起 1v1 通话，观察 `docker logs coturn` 是否出现 relay 分配记录。
