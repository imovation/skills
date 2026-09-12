# Federation（联邦通信）

## 通过 NPM 添加 Custom Location

在 NPM 面板 → 对应 Proxy Host → Custom Locations，或 Advanced Config 中添加：

```nginx
location = /.well-known/matrix/server {
    add_header Content-Type application/json;
    return 200 '{"m.server":"<你的域名>:443"}';
}
location = /.well-known/matrix/client {
    add_header Content-Type application/json;
    add_header Access-Control-Allow-Origin *;
    return 200 '{"m.homeserver":{"base_url":"https://<你的域名>"}}';
}
```

## 验证

```bash
curl -s https://<域名>/.well-known/matrix/server
curl -s https://<域名>/.well-known/matrix/client
```

## 端口

若要让外部服务器直接通过 8448 联邦，需要在云安全组放行 TCP 8448；
只走 443 + `.well-known` 委派时可不开放 8448。
