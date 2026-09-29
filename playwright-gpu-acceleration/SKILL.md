---
name: playwright-gpu-acceleration
description: 诊断并修复 Playwright E2E 测试过慢、测试期间 CPU 满载 / 笔记本风扇狂转、headless Chrome 明明有独立显卡却回落到软件 WebGL 渲染，以及截图基线（toHaveScreenshot / 像素比对）不匹配等问题。当用户提到「Playwright 测试很慢」「跑测试时风扇很响」「CPU 占用 100%」「明明有 GPU 为什么在 CPU 上渲染」「E2E 跑了好几个小时」「changed pixel ratio 超标」「截图对不上」「SwiftShader」「chrome-headless-shell」，或者在调整 Playwright 配置、排查 WebGL / Three.js / Canvas 场景渲染性能、评估无头浏览器能否启用硬件加速时，务必使用此 Skill。也适用于在断言「GPU 加速不可用」「无法启用硬件加速」之前。使用本 Skill 可避免重复走弯路：默认配置强制软件渲染、`channel` 单独无效、真正的开关是 `--in-process-gpu`，并提供像素基线失配的区域化归因方法。
---

# Playwright GPU 加速与性能诊断

解决「有 GPU 却跑在 CPU 上」导致 E2E 测试慢一个数量级、以及由此引发的风扇噪音和像素基线失配。

## 核心结论（先记住这三条）

1. **Playwright 默认强制软件 WebGL 渲染**。`chrome-headless-shell` 启动时带 `--use-angle=swiftshader-webgl`，所有 WebGL 光栅化跑在 CPU 上。
2. **`channel: 'chromium'` 单独无效**。换成完整浏览器后渲染后端仍是 SwiftShader —— 浏览器不是原因，参数才是。
3. **真正的开关是 `--in-process-gpu`**。沙箱化的 GPU **子进程**打不开 `/dev/dri/*` 与 `/dev/nvidia*`，导致 Vulkan 后端根本不被初始化；把 GPU 逻辑并入主进程后即可用上独显。

实测效果：真实 WebGL 负载（1920×1080，自定义着色器 + 2000 三角形 × 8 次绘制/帧）下，软件渲染 **21221 ms/帧** → 硬件加速 **99.6 ms/帧**，约 **213×**。单测试文件耗时从 1.6 小时降到 2.2 分钟。

## 第一步：永远先探测，不要猜

**唯一可靠的判定手段**是读取 WebGL 的 unmasked renderer 字符串。绝不要根据「有没有独显」「驱动装了没」下结论。

```bash
node scripts/probe-webgl-backend.mjs           # 默认配置
node scripts/probe-webgl-backend.mjs -- --use-angle=vulkan --in-process-gpu
```

判定表：

| `UNMASKED_RENDERER` 字符串 | 含义 |
|---|---|
| 含 `SwiftShader` | **纯 CPU 软件渲染** —— 问题就在这里 |
| 含 `ANGLE (NVIDIA` | 独显硬件加速 ✅ |
| 含 `Mesa Intel` / `ANGLE (Intel` | 集显硬件加速 ✅（仍然远好于 CPU） |
| `ok: false` / 无 context | 后端初始化失败，见下文排查阶梯 |

同时确认硬件本身是健康的（**探测方法要通用，不要照抄本机型号**）：

```bash
lspci -nn | grep -iE "vga|3d|display"   # 有哪些显卡
nvidia-smi                                # 独显驱动与占用
ls -l /dev/dri/                            # render 节点是否存在
```

## 为什么默认走 CPU

Playwright 会下载**两个** Chromium：

| 目录 | 体积 | GPU 支持 |
|---|---|---|
| `chromium_headless_shell-*` | ~262M | ❌ 阉割版，强制软件渲染 |
| `chromium-*` | ~379M | ✅ 完整浏览器，可启用硬件加速 |

`chrome-headless-shell` 是精简构建，捆绑了 SwiftShader 软件光栅化器，配合启动参数绕开硬件管线。**这不是硬件问题，也不是驱动问题。**

## 排查阶梯（按此顺序验证，不要跳步）

每一步都用 `probe-webgl-backend.mjs` 验证 renderer 字符串，确认后再进下一步。

| 步骤 | 动作 | 实测结论 |
|---|---|---|
| 1 | 换 `channel: 'chromium'` | **单独无效**，仍是 SwiftShader |
| 2 | 试 `--use-angle=gl`（集显） | ✅ 有效，但只到集显 |
| 3 | 试 `--use-angle=vulkan`（独显） | ❌ 失败：Vulkan 后端未初始化 |
| 4 | **加 `--in-process-gpu`** | ✅ **成功拿到独显** |

**第 3 步失败的根因**（这是最容易误判的地方）：沙箱化的 GPU 子进程**一个 `/dev/dri/*`、`/dev/nvidia*` 设备都没打开**。检查方法：

```bash
pgrep -f 'type=gpu-process' | while read pid; do
  echo "PID $pid: $(ls -l /proc/$pid/fd 2>/dev/null | grep -oE '/dev/(dri|nvidia)[a-z0-9]*' | sort -u | tr '\n' ',')"
done
# 输出 "(none)" = 设备没打开 = 沙箱拦截
```

`--in-process-gpu` 把 GPU 逻辑并入浏览器主进程，绕开这个子进程。

## 可直接复制的配置

```ts
// playwright.config.ts
use: {
  // ...原有配置
  launchOptions: {
    args: [
      '--no-sandbox',
      '--disable-gpu-sandbox',
      '--in-process-gpu',        // ← 关键项
      '--use-angle=vulkan',      // 独显；无独显时改 'gl'（集显）
      '--enable-features=Vulkan',
      '--ignore-gpu-blocklist',
    ],
  },
},
projects: [
  {
    name: 'Desktop',
    // ← 完整浏览器，缺它 --in-process-gpu 拿不到硬件后端
    use: { viewport: { width: 1920, height: 1080 }, channel: 'chromium' },
  },
],
```

**回退**：删掉 `launchOptions` 整块 + 各 project 的 `channel` 即可，无副作用。

## 必须知道的副作用

| 副作用 | 说明与应对 |
|---|---|
| **favicon 404 打断断言** | 完整 Chromium 会自动请求 `/favicon.ico`，缺文件产生 404 console error，被「console 零错误」断言拦下。在 `index.html` 加 `<link rel="icon" href="data:," />` |
| **GPU 崩溃升级为浏览器整体崩溃** | `--in-process-gpu` 后不再只是丢一个 GPU 子进程。换来数量级提速通常划算，但要知道这个权衡 |
| **基线绑定具体环境** | 像素基线绑定「GPU 型号 + 驱动版本 + 浏览器版本」。换任一环都需重采。CI 需固定环境 |
| 依赖已下载的完整浏览器 | `channel: 'chromium'` 需要 `~/.cache/ms-playwright/chromium-*`（非 headless_shell）存在 |

> **注意**：浏览器**不存在** CUDA / OptiX 选项。ANGLE 只有 `gl` / `vulkan` / `swiftshader` 三种后端，OptiX 不暴露给 WebGL（它是给离线渲染器与自研应用用的 SDK）。

## 像素基线失配：区域化归因法

基线对不上时，**不要直接归因为「GPU 渲染差异」**——先分区域量化，再下结论。

```bash
node scripts/pixel-diff-by-region.py <本次捕获.png> <基线.png>
```

它按 header / 左侧面板 / 3D 画布 / 右侧面板 / footer 分区统计变化像素比。典型判读：

| 现象 | 真正的原因 |
|---|---|
| 3D 画布占比极高、footer 干净 | 可能是真实 GPU 渲染差异（抗锯齿 / Bloom / 材质插值） |
| **footer 占比高** | **有走秒的时钟未冻结** —— 见下节 |
| 左侧面板数字变化 | 可能是 mock 数据漂移，**先确认采样时刻一致** |
| 差异集中在少数几行 | 特定元素（如阴影接触面）差异最大 |

### 基线里混入动态计时器（高频坑）

页面上的实时读数（`运行中 0:00:02`、`数据更新`、`xx FPS`）每次运行都不同，会**永久污染**像素基线。典型症状：即使在**同一个后端**下复跑也仍有微小失配。

**修法**：测试环境（`window.__E2E__` 或等价标记）下把这些读数钉死。常见做法是提前 return 掉计时器的 `useEffect`，或渲染固定占位值。排查清单：

- [ ] 页脚 / 状态栏的运行时长计时器
- [ ] 「数据更新时间」等时间戳
- [ ] FPS / 性能计数器
- [ ] 随机数生成的 mock 数据
- [ ] 自动轮播 / 动画元素

## A/B 对照纪律

**改任何配置前，先把同一条用例在改前 / 改后各跑一次。** 这是本次排查中唯一能稳定避免误判的习惯。

```bash
# 1. 记录改前基线
git stash push <配置文件>
pnpm exec playwright test <spec> --grep "<单个用例>" --reporter=line
# 2. 改后再跑同一条
git stash pop
pnpm exec playwright test <spec> --grep "<单个用例>" --reporter=line
```

只跑**单个**用例，别跑全量——快且足以对比。注意部分 spec 设计为整批运行（如遮挡读数需全部视角齐全），此时单跑会因「缺视角」失败，那与本次改动无关。

## 不要这样推断（实战反面案例）

以下四种推断都曾导致错误结论，代价是几十分钟的排查：

| 错误推断 | 实测否证方式 |
|---|---|
| 「加 `channel: 'chromium'` 就能用上 GPU」 | 加了之后 renderer 字符串**仍是 SwiftShader** |
| 「Vulkan loader 版本低于 ICD 声明版本，会拒绝加载」 | loader 正常枚举并加载了驱动，版本差不是原因 |
| 「GPU 节点权限不足导致失败」 | `id` 显示用户**本就在 `render` 组**且设备可读写 |
| 「基线失配是 mock 数据漂移」 | 错在**拿不同时刻的两张截图**对比；数据其实是稳定的 |

**通用教训**：
- 任何「环境有问题」的判断，都要用一条**只读探测命令**验证，别靠推理。
- 任何「数据在变」的判断，先确认**采样时刻一致**。
- 拿不到证据时，优先跑 A/B 对照，而不是继续加参数。

## 性能验证

配置改完后，用真实负载测吞吐，别用 `gl.finish()` 之类的空转测法（它不保证同步，会得到 `0 ms` 的假数据）：

```bash
node scripts/benchmark-webgl.mjs gpu    # 或 intel / sw
```

同时看这几项：单帧耗时、`nvidia-smi` 显存占用、系统 load average、CPU 封装温度。

## 参考资料

- `references/troubleshooting.md` —— 完整失败模式与判读表（Vulkan 报 `device memory allocation has failed`、GL 上下文丢失、混合显卡未选中独显等）
- `scripts/probe-webgl-backend.mjs` —— 判定渲染后端
- `scripts/benchmark-webgl.mjs` —— 三后端吞吐对比
- `scripts/pixel-diff-by-region.py` —— 像素基线分区归因
