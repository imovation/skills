---
name: matrix-self-host-expert
description: 专门用于在 Linux 服务器上自动化部署和维护私有 Matrix (Synapse) 通信基座。当用户需要绕过 QQ/飞书等平台的限制（如不支持 /focus 或会话绑定），或者想要在国内无魔法环境下获得最佳 OpenClaw 体验时，务必使用此 Skill。该 Skill 包含了针对国内阿里云/腾讯云环境的镜像加速、数据库 Locale 冲突修复及 HTTPS 自动配置等硬核实战经验。
---

# Matrix 自建专家 (Matrix Self-Host Expert)

本 Skill 旨在帮助用户在 Ubuntu/Debian 服务器上快速构建一套生产级别的 Matrix 通信环境。

## 核心工作流

### 1. 环境准备与加速
- **OS**: 优先推荐 Ubuntu 24.04/22.04。
- **Docker**: 必须配置国内镜像加速器（如阿里云、华为云 ddn-k8s），以解决国内拉取 `matrixdotorg/synapse` 镜像 403 的问题。
- **端口**: 必须确保安全组放行 80, 443, 81 (NPM), 8008 (Synapse)。

### 2. 部署架构
使用 Docker Compose 编排以下三个核心容器：
- **db (Postgres 14-alpine)**: 存储消息与用户数据。
- **synapse**: Matrix 核心服务端。
- **npm (Nginx Proxy Manager)**: 可视化反向代理与 SSL 证书管理。

### 3. 常见“地雷”修复逻辑（关键指令）
如果容器出现重启循环，请按以下逻辑自动修复：

#### A. 注册校验地雷 (ConfigError)
如果开启了 `enable_registration: true`，必须同时在 `homeserver.yaml` 根路径添加：
`enable_registration_without_verification: true`

#### B. 数据库 Locale 冲突 (IncorrectDatabaseSetup)
当报错 Collation 应该为 'C' 而非 'en_US.utf8' 时，在 `homeserver.yaml` 的 `database` 配置块（注意不是 args 内部，是顶级）添加：
`allow_unsafe_locale: true`

#### C. 权限地雷
确保对数据目录执行 `chmod -R 777 ./synapsedata`。

## 常用脚本资源

### 一键注册账号脚本
```bash
docker exec -it matrix-synapse-1 register_new_matrix_user http://localhost:8008 \
    -c /data/homeserver.yaml \
    -u [用户名] \
    -p [密码] \
    --admin
```

### 推荐的 NPM 配置项
- **Forward Hostname**: `synapse`
- **Forward Port**: `8008`
- **SSL**: 开启 `Force SSL` 和 `HTTP/2`。

## 注意事项
- 提醒用户 Matrix 默认不支持删除消息的物理擦除（去中心化特性）。
- 部署完成后建议关闭开放注册，改为手动创建账号。
