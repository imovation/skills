#!/bin/bash
# ./register_user.sh <用户名> <密码>              → 普通用户
# ./register_user.sh <用户名> <密码> --admin      → 管理员
docker exec matrix-synapse register_new_matrix_user http://localhost:8008 \
    -c /data/homeserver.yaml -u "$1" -p "$2" $3
