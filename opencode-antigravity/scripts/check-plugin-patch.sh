#!/usr/bin/env bash
# 检查 opencode-antigravity-auth 插件(包缓存副本)的变体重试补丁是否在位
# 背景: daily 沙箱模型清单动态漂移,裸名/别名经常 404,补丁在 404 时自动轮换候选模型名
# 用法: check-plugin-patch.sh            → PATCHED / VANILLA / NOT_FOUND
#       check-plugin-patch.sh --fix      → 自动重新打补丁
set -uo pipefail

CACHE="$HOME/.cache/opencode/packages"
FIX="${1:-}"

F=""
for d in "$CACHE/opencode-antigravity-auth@latest" "$CACHE/opencode-antigravity-auth"; do
  c="$d/node_modules/opencode-antigravity-auth/dist/src/plugin.js"
  [ -f "$c" ] && { F="$c"; break; }
done
[ -z "$F" ] && { echo "NOT_FOUND: 未找到插件包缓存副本"; exit 2; }

UA_MARK="daily 端点按 UA 指纹放行模型实体"
VAR_MARK="daily 沙箱模型清单动态漂移"
if grep -q "$VAR_MARK" "$F" && grep -q "$UA_MARK" "$F"; then
  echo "PATCHED: $F"
else
  echo "VANILLA: $F (缺:$(grep -q "$VAR_MARK" "$F" || echo -n ' 变体重试')$(grep -q "$UA_MARK" "$F" || echo -n ' UA覆写'))"
  if [ "$FIX" = "--fix" ]; then
    python3 - "$F" <<'PYEOF'
import sys
p = sys.argv[1]
src = open(p).read()
old = 'const response = await fetch(prepared.request, prepared.init);'
new = '''let response = await fetch(prepared.request, prepared.init);
                                        // P-opencode(2026-08-25): daily 沙箱模型清单动态漂移,404 时自动轮换候选模型名
                                        try {
                                            const __u = new URL(String(prepared.request));
                                            if (response.status === 404 && /cloudcode-pa/.test(__u.hostname)) {
                                                const __b = JSON.parse(String(prepared.init?.body ?? "{}"));
                                                const __base = String(__b.model ?? "");
                                                const __cands = [];
                                                const __push = (v) => { if (v && v !== __base && !__cands.includes(v)) __cands.push(v); };
                                                const __dash = __base.replace(/\\.(\\d)/g, "-$1");
                                                const __dot = __base.replace(/-(\\d)/g, ".$1");
                                                __push(__dash); __push(__dot);
                                                for (const __bb of [__base, __dash, __dot]) {
                                                    for (const __s of ["low", "medium", "high", "minimal"]) __push(__bb + "-" + __s);
                                                }
                                                for (const __cand of __cands.slice(0, 10)) {
                                                    __b.model = __cand;
                                                    if (__b.request && __b.request.model) __b.request.model = __cand;
                                                    const __init2 = { ...prepared.init, body: JSON.stringify(__b) };
                                                    const __r2 = await fetch(__u.toString(), __init2);
                                                    if (__r2.status !== 404) { response = __r2; break; }
                                                    try { await __r2.text(); } catch {}
                                                }
                                            }
                                        } catch {}'''
if old not in src:
    print("FIX_FAILED: 锚点不存在(插件结构可能已变)"); sys.exit(1)
src = src.replace(old, new, 1)
ua_old = 'let response = await fetch(prepared.request, prepared.init);'
if 'P-opencode-UA' not in src:
    ua_ins = ('try { const __hu = new URL(String(prepared.request)); if (/cloudcode-pa/.test(__hu.hostname)) { const __hh = prepared.init?.headers; '
              'const __cliUA = "antigravity/cli/1.1.13 (aidev_client; os_type=linux; arch=amd64; cl=964361259; auth_method=consumer)"; '
              'if (__hh && typeof __hh.set === "function") __hh.set("User-Agent", __cliUA); else if (__hh) { __hh["User-Agent"] = __cliUA; delete __hh["user-agent"]; } } } catch {}\n'
              '                                        // P-opencode-UA(2026-08-25): daily 端点按 UA 指纹放行模型实体,IDE 风格 UA 会被 404\n'
              + ua_old)
    src = src.replace(ua_old, ua_ins, 1)
open(p, 'w').write(src)
print("FIXED")
PYEOF
    node --check "$F" && echo "语法OK" || echo "语法错误!"
  fi
fi
