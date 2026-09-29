#!/usr/bin/env node
/**
 * 判定 Playwright/Chromium 实际使用的 WebGL 渲染后端。
 *
 * 这是判断「有没有用上硬件加速」的唯一可靠手段 —— 不要根据显卡型号、
 * 驱动是否安装、或启动参数去推测，必须读 UNMASKED_RENDERER 字符串。
 *
 * 用法：
 *   node probe-webgl-backend.mjs                        # 默认配置
 *   node probe-webgl-backend.mjs --use-angle=gl         # 追加启动参数
 *   node probe-webgl-backend.mjs --channel=chromium     # 用完整浏览器
 *
 * 判读：
 *   含 SwiftShader          → 纯 CPU 软件渲染（问题所在）
 *   含 ANGLE (NVIDIA        → 独显硬件加速
 *   含 Mesa Intel / ANGLE (Intel → 集显硬件加速
 *   ok:false                → 后端初始化失败，见 references/troubleshooting.md
 *
 * 依赖：本机任意项目下的 playwright-core。找不到时用 PW_CORE 环境变量指定。
 */
import { createRequire } from 'node:module'
import { execSync } from 'node:child_process'
import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

function findPlaywrightCore() {
  if (process.env.PW_CORE && existsSync(process.env.PW_CORE)) return process.env.PW_CORE
  const require = createRequire(import.meta.url)
  for (const base of [process.cwd(), '/home/imovation/projects/mirror-park']) {
    try {
      return require.resolve('playwright-core', { paths: [base] })
    } catch { /* 继续找 */ }
  }
  // 退而求其次：扫 node_modules/.pnpm
  for (const base of [process.cwd(), '/home/imovation/projects/mirror-park']) {
    const pnpm = join(base, 'node_modules', '.pnpm')
    if (!existsSync(pnpm)) continue
    const hit = readdirSync(pnpm).find(d => d.startsWith('playwright-core@'))
    if (hit) {
      const p = join(pnpm, hit, 'node_modules', 'playwright-core', 'index.mjs')
      if (existsSync(p)) return p
    }
  }
  throw new Error(
    '找不到 playwright-core。请在项目目录下运行，或用 PW_CORE=<路径> 指定。',
  )
}

const argv = process.argv.slice(2)
const channel = (argv.find(a => a.startsWith('--channel=')) || '').split('=')[1]
const extraArgs = argv.filter(a => !a.startsWith('--channel='))

const { chromium } = await import(findPlaywrightCore())

const base = ['--no-sandbox', '--disable-gpu-sandbox', '--enable-unsafe-swiftshader']
const launch = { args: [...base, ...extraArgs] }
if (channel) launch.channel = channel

console.log('启动参数:', [...base, ...extraArgs].join(' '))
if (channel) console.log('channel :', channel)
console.log('')

let browser
try {
  browser = await chromium.launch(launch)
} catch (e) {
  console.log(JSON.stringify({ ok: false, reason: 'launch failed', detail: String(e).split('\n')[0] }, null, 2))
  process.exit(1)
}

const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
await page.goto('data:text/html,<canvas id=c width=1920 height=1080></canvas>')

const result = await page.evaluate(() => {
  const c = document.getElementById('c')
  const gl = c.getContext('webgl2') || c.getContext('webgl')
  if (!gl) return { ok: false, reason: 'no WebGL context' }
  const dbg = gl.getExtension('WEBGL_debug_renderer_info')
  return {
    ok: true,
    vendor: gl.getParameter(gl.VENDOR),
    renderer: gl.getParameter(gl.RENDERER),
    unmasked: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
    contextLost: gl.isContextLost(),
  }
})

console.log(JSON.stringify(result, null, 2))

if (result.ok) {
  const u = String(result.unmasked || '')
  const backend = /swiftshader/i.test(u) ? '❌ 纯 CPU 软件渲染'
    : /NVIDIA/i.test(u) ? '✅ 独显硬件加速'
    : /Intel|Mesa|AMD|Radeon/i.test(u) ? '✅ 集显硬件加速'
    : '❓ 无法判定'
  console.log('\n判定:', backend)
  if (/swiftshader/i.test(u)) {
    console.log('\n下一步：见 SKILL.md「排查阶梯」。注意单独加 channel 无效，')
    console.log('        关键参数是 --in-process-gpu。')
  }
}

// GPU 子进程是否打开了 DRI / NVIDIA 设备（诊断沙箱拦截）
try {
  const pids = execSync("pgrep -f 'type=gpu-process' | tr '\\n' ' '").toString().trim().split(' ').filter(Boolean)
  for (const pid of pids) {
    let fds = '(进程已退出)'
    try {
      fds = execSync(`ls -l /proc/${pid}/fd 2>/dev/null | grep -oE '/dev/(dri|nvidia)[a-z0-9]*' | sort -u | tr '\\n' ','`).toString().trim() || '(none)'
    } catch { /* ignore */ }
    console.log(`\nGPU 子进程 ${pid} 打开的设备: ${fds}`)
    if (fds === '(none)') {
      console.log('  ↑ 一个设备都没打开 = 沙箱拦截，Vulkan/硬件后端无法初始化。')
      console.log('    解法：加 --in-process-gpu')
    }
  }
} catch { /* 无 GPU 子进程，忽略 */ }

await browser.close()
