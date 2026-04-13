#!/usr/bin/env bash
# OpenClaw Matrix ACP Deduplicate Patch
# 修复 Matrix 渠道 ACP 会话重复回复问题
#
# 用法：
#   bash patch-matrix-dedupe.sh --apply    应用修补
#   bash patch-matrix-dedupe.sh --check    检查当前是否已修补
#   bash patch-matrix-dedupe.sh --rollback 回滚到备份

set -euo pipefail

OPENCLAW_BIN="${OPENCLAW_BIN:-$(which openclaw 2>/dev/null || true)}"

if [ -z "$OPENCLAW_BIN" ]; then
    echo "错误：找不到 openclaw 命令，请确认已安装或设置 OPENCLAW_BIN 环境变量" >&2
    exit 1
fi

OPENCLAW_DIR="$(dirname "$(dirname "$OPENCLAW_BIN")")/lib/node_modules/openclaw"

if [ ! -d "$OPENCLAW_DIR/dist" ]; then
    echo "错误：找不到 OpenClaw dist 目录: $OPENCLAW_DIR/dist" >&2
    exit 1
fi

find_matrix_plugin() {
    local candidates
    candidates=$(find "$OPENCLAW_DIR/dist" -maxdepth 1 -name 'channel-BT7*.js' -o -name 'channel-*matrix*.js' 2>/dev/null | head -5)

    if [ -z "$candidates" ]; then
        candidates=$(grep -rl "matrixPlugin" "$OPENCLAW_DIR/dist/" --include='channel-*.js' 2>/dev/null | head -5)
    fi

    for f in $candidates; do
        if grep -q 'deliveryMode: "direct"' "$f" && grep -q 'matrixPlugin' "$f"; then
            echo "$f"
            return 0
        fi
    done

    echo "" >&2
    echo "错误：无法定位 Matrix 渠道插件文件" >&2
    echo "请手动在 $OPENCLAW_DIR/dist/ 中搜索包含 'matrixPlugin' 和 'outbound' 的 JS 文件" >&2
    return 1
}

PLUGIN_FILE=$(find_matrix_plugin) || exit 1

if [ -z "$PLUGIN_FILE" ]; then
    exit 1
fi

echo "Matrix 插件文件: $PLUGIN_FILE"

do_check() {
    echo "--- 检查修补状态 ---"

    if grep -q 'shouldTreatDeliveredTextAsVisible' "$PLUGIN_FILE"; then
        local context
        context=$(grep -B2 -A2 'shouldTreatDeliveredTextAsVisible' "$PLUGIN_FILE" | head -10)
        echo "✅ 已修补 — 找到 shouldTreatDeliveredTextAsVisible 方法"
        echo ""
        echo "上下文："
        echo "$context"
    else
        echo "❌ 未修补 — Matrix 插件缺少 shouldTreatDeliveredTextAsVisible"
        echo "   运行 'bash $0 --apply' 来应用修补"
    fi
}

do_apply() {
    echo "--- 应用修补 ---"

    if grep -q 'shouldTreatDeliveredTextAsVisible' "$PLUGIN_FILE"; then
        local in_outbound
        # 确认该方法在 outbound 对象内部（紧跟 deliveryMode 行之后）
        in_outbound=$(grep -c 'shouldTreatDeliveredTextAsVisible' "$PLUGIN_FILE" || true)
        echo "⚠️  文件中已存在 shouldTreatDeliveredTextAsVisible（共 $in_outbound 处），跳过修补"
        echo "   如果修补不生效，请检查该方法是否在 Matrix 的 outbound 对象内"
        return 0
    fi

    local backup="${PLUGIN_FILE}.bak"
    if [ ! -f "$backup" ]; then
        cp "$PLUGIN_FILE" "$backup"
        echo "✅ 备份已创建: $backup"
    else
        echo "ℹ️  备份已存在: $backup"
    fi

    # 使用 Python 精确替换，避免 sed 在压缩 JS 中的多行匹配问题
    local patch_line='shouldTreatDeliveredTextAsVisible: (params) => params.kind === "block" && typeof params.text === "string" && params.text.trim().length > 0,'
    local anchor='deliveryMode: "direct",'

    if grep -q "$anchor" "$PLUGIN_FILE"; then
        python3 -c "
import sys, re
filepath = sys.argv[1]
anchor = sys.argv[2]
patch_line = sys.argv[3]

with open(filepath, 'r') as f:
    content = f.read()

# 在 outbound 的 deliveryMode: "direct", 后面插入 patch_line
# 匹配 deliveryMode: "direct" 后紧跟的换行（可能有制表符或空格），然后是 chunker 或 shouldTreat
pattern = r'(deliveryMode: \"direct\",\n)'
replacement = r'\1' + '\t' + patch_line + '\n'
new_content = re.sub(pattern, replacement, content, count=1)

if new_content == content:
    print('ERROR: 替换未生效，可能文件格式不符预期')
    sys.exit(1)

with open(filepath, 'w') as f:
    f.write(new_content)
print('OK')
" "$PLUGIN_FILE" "$anchor" "$patch_line"
        local rc=$?
        if [ $rc -eq 0 ]; then
            echo "✅ 修补已应用"
        else
            echo "⚠️  自动替换失败，需要手动修补"
            echo "   参考 SKILL.md 中的手动修补步骤"
            return 1
        fi
    else
        echo "⚠️  未找到预期的修补锚点 'deliveryMode: \"direct\"'"
        echo "   文件结构可能已变更，需要手动修补"
        echo "   参考 SKILL.md 中的手动修补步骤"
        return 1
    fi

    echo ""
    echo "⚠️  请重启 Gateway 使修补生效："
    echo "   openclaw gateway restart"
}

do_rollback() {
    echo "--- 回滚修补 ---"

    local backup="${PLUGIN_FILE}.bak"

    if [ ! -f "$backup" ]; then
        echo "❌ 未找到备份文件: $backup"
        return 1
    fi

    cp "$backup" "$PLUGIN_FILE"
    echo "✅ 已从备份恢复: $backup"
    echo ""
    echo "⚠️  请重启 Gateway 使恢复生效："
    echo "   openclaw gateway restart"
}

case "${1:-}" in
    --apply)
        do_apply
        ;;
    --check)
        do_check
        ;;
    --rollback)
        do_rollback
        ;;
    *)
        echo "OpenClaw Matrix ACP 去重修补工具"
        echo ""
        echo "用法："
        echo "  bash $0 --apply     应用修补（需重启 Gateway）"
        echo "  bash $0 --check     检查当前修补状态"
        echo "  bash $0 --rollback  从备份恢复原始文件"
        echo ""
        echo "修复内容："
        echo "  在 Matrix 渠道插件的 outbound 对象中添加"
        echo "  shouldTreatDeliveredTextAsVisible 方法，阻止 ACP 回复"
        echo "  被重复投递（block reply + final fallback）"
        ;;
esac