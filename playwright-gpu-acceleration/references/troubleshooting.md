# 失败模式与判读表

按「症状 → 可能原因 → 验证命令 → 处理」组织。**任何判断都要先用验证命令取证，不要靠推理。**

---

## 一、`--use-angle=vulkan` 失败

### 症状 A：无 WebGL context / `ok: false`

```bash
node scripts/probe-webgl-backend.mjs --channel=chromium --use-angle=vulkan
```

### 症状 B：ANGLE 报 `device memory allocation has failed`（Vulkan 错误码 -2）

```
Internal Vulkan error (-2): A device memory allocation has failed.
  at vk_helpers.cpp initExternalMemory
→ GL_OUT_OF_MEMORY → GL_CONTEXT_LOST_KHR
```

| 可能原因 | 验证命令 | 结论 |
|---|---|---|
| 显存不足 | `nvidia-smi --query-gpu=memory.used,memory.total --format=csv` | 排除：独显通常有十几 GB 空闲 |
| GPU 进程被沙箱隔离 | `ls -l /proc/<gpu-pid>/fd \| grep /dev/nvidia` | **最常见**，见下 |
| 驱动/浏览器版本不兼容 | 查驱动版本 vs Chromium 版本 | 换浏览器版本可能解决 |

**已排除的伪原因**（都曾导致误判）：

- ❌「Vulkan loader 版本低于 ICD 声明版本会被拒绝」——实测 loader 正常枚举并加载了驱动。
  验证：`vkEnumerateInstanceVersion` + 看 loader 是否有相关报错。
- ❌「用户不在 `render` 组所以没权限」——**先跑 `id` 确认**。多数桌面环境的用户本就在该组。
  验证：`id` + `ls -l /dev/dri/renderD*` + `os.open()` 实测读写。

### 决定性验证：GPU 进程打开了哪些设备

```bash
for pid in $(pgrep -f 'type=gpu-process'); do
  echo "PID $pid: $(ls -l /proc/$pid/fd 2>/dev/null | grep -oE '/dev/(dri|nvidia)[a-z0-9]*' | sort -u | tr '\n' ',')"
done
```

| 输出 | 含义 |
|---|---|
| 有 `/dev/nvidia*` 或 `/dev/dri/renderD*` | 沙箱没拦，问题在驱动侧 |
| **`(none)`** | **沙箱拦截**，硬件后端根本没机会初始化 → 用 `--in-process-gpu` |

补充：Chrome 日志里搜 `vulkan` 关键字。**一条都没有** = 后端压根没被初始化（而非初始化后失败）。

```bash
$CHROME --headless --no-sandbox --use-angle=vulkan --enable-logging=stderr --v=1 \
  --dump-dom about:blank 2>&1 | grep -i vulkan
```

---

## 二、`--in-process-gpu` 相关

| 症状 | 处理 |
|---|---|
| 加上后 GPU 崩溃导致**整个浏览器**退出 | 已知权衡：原本只丢 GPU 子进程，现在整个浏览器挂。降级方案见下 |
| 需要退回独立 GPU 进程 | 去掉 `--in-process-gpu`，改用 `--use-angle=gl`（集显），仍远好于 CPU |

**降级路径**：`--in-process-gpu` + `vulkan` → `--in-process-gpu` + `gl`（集显）→ 仅 `gl`（仍需完整浏览器）。

---

## 三、混合显卡：独显不被选中

无头模式下浏览器可能只枚举到集显。验证：

```bash
node scripts/probe-webgl-backend.mjs --channel=chromium --in-process-gpu --use-angle=vulkan
# 看到 ANGLE (Intel…) 或 Mesa Intel… 说明选的是集显
```

处理：
1. 确认独显驱动正常（`nvidia-smi`）
2. 试 `--use-angle=gl`（有时反而能走 EGL 拿到独显）
3. 接受集显——对本类场景通常已足够（实测集显 ≈ 12× 于软件渲染）

---

## 四、像素基线失配

**第一步永远是区域化归因**，不要直接归因为「GPU 差异」。

```bash
node scripts/pixel-diff-by-region.py 本次.png 基线.png
```

| 判读 | 真凶 | 处理 |
|---|---|---|
| 3D 画布占比极高、footer 干净 | 真实渲染差异（抗锯齿/Bloom/材质插值） | 重采基线；或确认换环境再采 |
| **footer 占比高** | 走秒时钟/FPS 计数器未冻结 | 在测试环境下把这些读数钉死 |
| 左侧面板数字变化 | mock 数据漂移 | 确认采样时刻一致；改用固定 fixture |
| 同一后端复跑仍有微小失配 | 必然有非确定性来源 | 逐项排查清单 |

### 必查的非确定性来源清单

- [ ] 页脚运行时长 / 计时器
- [ ] 「数据更新时间」时间戳
- [ ] FPS / 性能计数器
- [ ] `Math.random()` / faker 生成的 mock 数据
- [ ] 自动轮播、动画、光标闪烁
- [ ] 真实时钟（页头数字时钟）

### 归因陷阱

**不要拿不同时刻的两张截图做对比。** 曾据此误判「mock 数据漂移」，实际数据完全稳定。

正确做法：同一条用例、同一配置、连续两次运行，两次之间的差异才是真实非确定性来源。

### 重采基线

```bash
# 显式更新模式（切勿用普通模式「改到通过为止」）
UPDATE_FIDELITY_BASELINES=1 pnpm exec playwright test <spec> --grep "<单个用例>"

# 必须再做普通模式复跑，确认真的是稳定匹配而非写完即过
pnpm exec playwright test <spec> --grep "<单个用例>"
```

判断是否真稳定：连续复跑 2 次，全部通过且基线文件 hash 不变。

---

## 五、性能测量陷阱

| 陷阱 | 说明 | 正确做法 |
|---|---|---|
| 用 `gl.finish()` 测时 | 不保证同步，会得到 `0 ms` 假数据 | 用 `gl.readPixels()` 强制同步 |
| 分两次 `page.evaluate` | 软件渲染会丢上下文，第二次测到死上下文 | 探测与测速放同一次 evaluate |
| 不检查 `isContextLost()` | 拿到的是死上下文的数字 | 测完检查，丢失则明确报告 |
| 只测 `clear()` | 不反映真实绘制成本 | 加 `drawArrays` + 真实着色器 |
| 高负载不 yield | 触发 Chrome GPU 看门狗杀进程 | 帧间 `await new Promise(r => setTimeout(r, 0))` |

软件渲染的典型表现：上下文在数秒后丢失。**这本身就是有价值的证据** —— 说明它无法承载真实 WebGL 负载。

---

## 六、排查期间的常见误判

| 错误推断 | 正确取证方式 |
|---|---|
| 「有 GPU / 装了驱动，所以应该走硬件」 | 读 `UNMASKED_RENDERER` |
| 「换完整浏览器就能用 GPU」 | 换完再读一次 renderer（很可能仍是 SwiftShader） |
| 「报错信息说的就是原因」 | 报错常是次生现象，真因在更早的初始化阶段 |
| 「权限不足」 | `id` 确认组 + `os.open()` 实测读写 |
| 「加了参数没效果，说明无法启用」 | 参数顺序与组合可能不对；查排查阶梯是否走完 |
| 「测试慢了是机器慢」 | 读 `UNMASKED_RENDERER` + `nproc` + load average，三者一起看 |

**通用纪律**：改任何配置前，先把同一条用例在改前 / 改后各跑一次（A/B 对照）。缺对照组时，推理错误几乎必然发生。
