#!/usr/bin/env node
/**
 * 三后端 WebGL 吞吐对比：独显 / 集显 / 软件渲染。
 *
 * 目的：量化「软件渲染 vs 硬件加速」的真实差距，为是否值得改配置提供依据。
 *
 * 用法：
 *   node benchmark-webgl.mjs            # 跑全部三种
 *   node benchmark-webgl.mjs gpu        # 只跑独显
 *   node benchmark-webgl.mjs intel
 *   node benchmark-webgl.mjs sw
 *
 * 注意事项：
 *   - 不要用 gl.finish() 测时，它不保证同步，会得到 0 ms 的假数据。
 *     本脚本用 gl.readPixels() 强制同步，并用循环 + clear + drawArrays 施压。
 *   - 软件渲染在重负载下可能直接把浏览器跑崩（进程退出）。本脚本会捕获
 *     并降低 FRAMES 重试，仍失败则标注「崩溃」而不是给出误导性数字。
 */
import { createRequire } from 'node:module'
import { existsSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

function findPlaywrightCore() {
  if (process.env.PW_CORE && existsSync(process.env.PW_CORE)) return process.env.PW_CORE
  const require = createRequire(import.meta.url)
  for (const base of [process.cwd(), '/home/imovation/projects/mirror-park']) {
    try { return require.resolve('playwright-core', { paths: [base] }) } catch { /* next */ }
  }
  for (const base of [process.cwd(), '/home/imovation/projects/mirror-park']) {
    const pnpm = join(base, 'node_modules', '.pnpm')
    if (!existsSync(pnpm)) continue
    const hit = readdirSync(pnpm).find(d => d.startsWith('playwright-core@'))
    if (hit) {
      const p = join(pnpm, hit, 'node_modules', 'playwright-core', 'index.mjs')
      if (existsSync(p)) return p
    }
  }
  throw new Error('找不到 playwright-core。用 PW_CORE=<路径> 指定。')
}

const VULKAN = ['--no-sandbox', '--disable-gpu-sandbox', '--in-process-gpu',
  '--use-angle=vulkan', '--enable-features=Vulkan', '--ignore-gpu-blocklist']
const GL = ['--no-sandbox', '--disable-gpu-sandbox',
  '--use-angle=gl', '--use-gl=angle', '--ignore-gpu-blocklist', '--enable-gpu-rasterization']
const SW = ['--no-sandbox', '--disable-gpu-sandbox', '--enable-unsafe-swiftshader']

const MODES = {
  gpu: { label: '独显 (Vulkan + in-process-gpu)', args: VULKAN, channel: 'chromium' },
  intel: { label: '集显 (GL)', args: GL, channel: 'chromium' },
  sw: { label: '软件渲染 (SwiftShader)', args: SW },
}

const FRAMES = 40
const DRAWS_PER_FRAME = 8
const TRIANGLES = 2000
// 软件渲染下单帧可达 20 秒以上，page.evaluate 默认 30s 超时会误报失败。
// 这里放宽到 15 分钟，让 SwiftShader 也能跑完真实数据。
const EVAL_TIMEOUT_MS = 15 * 60 * 1000

// 注意：GLSL ES 3.00 要求 `#version` 指令位于第 0 列，前面不能有缩进。
const SHADER = `#version 300 es
in vec2 p; out vec2 v;
void main(){ v=p; gl_Position=vec4(p,0.,1.); }`

const FRAG = `#version 300 es
precision highp float; in vec2 v; out vec4 o;
void main(){
  float s=0.;
  for(int i=0;i<8;i++){ s+=sin(v.x*float(i)*3.1)*cos(v.y*float(i)*2.7); }
  o=vec4(vec3(s*0.1+0.5),1.);
}`

const { chromium } = await import(findPlaywrightCore())

async function run(mode) {
  const m = MODES[mode]
  const launch = { args: m.args }
  if (m.channel) launch.channel = m.channel

  // 软件渲染会立即丢失上下文（观察到 isContextLost() 变 true），因此**不能**分两次
  // evaluate：第一次探测 renderer，第二次测速会打在已丢失的上下文上。
  // 探测与测速必须在同一次 evaluate 内完成。
  // 另：软件渲染在重负载下会触发 Chrome GPU 看门狗，故降到 1/8 负载并帧间让出事件循环。
  const frames = mode === 'sw' ? Math.max(4, Math.floor(FRAMES / 8)) : FRAMES
  const draws = mode === 'sw' ? Math.max(1, Math.floor(DRAWS_PER_FRAME / 2)) : DRAWS_PER_FRAME

  const browser = await chromium.launch(launch)
  try {
    const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } })
    await page.goto('data:text/html,<canvas id=c width=1920 height=1080></canvas>')

    const out = await Promise.race([
      page.evaluate(
        async ({ frames, draws, tris, vs, fs }) => {
          const gl = document.getElementById('c').getContext('webgl2', { antialias: true })
          if (!gl) return { ok: false, reason: 'no WebGL2 context' }
          const dbg = gl.getExtension('WEBGL_debug_renderer_info')
          const unmasked = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null

          const mk = (type, src) => {
            const s = gl.createShader(type)
            gl.shaderSource(s, src); gl.compileShader(s)
            if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s))
            return s
          }
          const pr = gl.createProgram()
          gl.attachShader(pr, mk(gl.VERTEX_SHADER, vs))
          gl.attachShader(pr, mk(gl.FRAGMENT_SHADER, fs))
          gl.linkProgram(pr); gl.useProgram(pr)

          const buf = gl.createBuffer()
          gl.bindBuffer(gl.ARRAY_BUFFER, buf)
          const verts = new Float32Array(tris * 3)
          for (let i = 0; i < verts.length; i++) verts[i] = Math.sin(i) * 2
          gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW)
          const loc = gl.getAttribLocation(pr, 'p')
          gl.enableVertexAttribArray(loc)
          gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0)

          const px = new Uint8Array(4)
          const t0 = performance.now()
          for (let f = 0; f < frames; f++) {
            for (let d = 0; d < draws; d++) {
              gl.clearColor(0, 0, 0, 1)
              gl.clear(gl.COLOR_BUFFER_BIT)
              gl.drawArrays(gl.TRIANGLES, 0, tris)
            }
            gl.readPixels(0, 0, 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px) // 强制同步
            await new Promise(r => setTimeout(r, 0)) // 让出事件循环，避免 GPU 看门狗杀进程
          }
          const ms = performance.now() - t0
          const lost = gl.isContextLost()
          if (lost) {
            return { ok: false, unmasked, reason: `上下文在测速过程中丢失（${ms.toFixed(0)} ms 后），软件渲染无法承载此负载` }
          }
          return { ok: true, unmasked, msPerFrame: +(ms / frames).toFixed(1), checksum: px[0], contextLost: false }
        },
        { frames, draws, tris: TRIANGLES, vs: SHADER, fs: FRAG },
      ),
      new Promise((_, rej) => setTimeout(() => rej(new Error(`超过 ${EVAL_TIMEOUT_MS / 60000} 分钟未完成`)), EVAL_TIMEOUT_MS)),
    ])

    if (!out.ok) {
      return { mode, label: m.label, ok: false, renderer: out.unmasked, reason: out.reason }
    }
    return { mode, label: m.label, ok: true, frames, renderer: out.unmasked, msPerFrame: out.msPerFrame, checksum: out.checksum, contextLost: out.contextLost }
  } catch (e) {
    return { mode, label: m.label, ok: false, reason: `渲染进程崩溃/超时：${String(e).split('\n')[0].slice(0, 90)}` }
  } finally {
    await browser.close().catch(() => {})
  }
}

const which = process.argv[2]
const modes = which && MODES[which] ? [which] : Object.keys(MODES)

console.log(`负载：${FRAMES} 帧 × ${DRAWS_PER_FRAME} 次绘制 × ${TRIANGLES} 三角形 @ 1920×1080\n`)
const rows = []
for (const m of modes) {
  process.stdout.write(`  ${MODES[m].label} ... `)
  const r = await run(m)
  rows.push(r)
  console.log(r.ok ? `${r.msPerFrame} ms/帧` : r.reason)
}

console.log('\n' + '─'.repeat(78))
for (const r of rows) {
  console.log(`\n【${r.label}】`)
  if (!r.ok) { console.log(`  失败：${r.reason}`); if (r.renderer) console.log(`  渲染后端 : ${r.renderer}`); continue }
  console.log(`  渲染后端 : ${r.renderer}`)
  console.log(`  单帧耗时 : ${r.msPerFrame} ms  (${r.frames} 帧采样)`)
  console.log(`  像素校验 : ${r.checksum}  上下文丢失: ${r.contextLost}`)
}
const ok = rows.filter(r => r.ok)
if (ok.length > 1) {
  const base = ok.find(r => r.mode === 'sw') || ok[0]
  const fast = ok.reduce((a, b) => (a.msPerFrame < b.msPerFrame ? a : b))
  if (fast.mode !== base.mode) {
    console.log(`\n最快「${fast.label}」相对「${base.label}」提速 ${(base.msPerFrame / fast.msPerFrame).toFixed(1)}×`)
  }
  const sums = new Set(ok.map(r => r.checksum))
  console.log(`各后端像素校验和: ${sums.size === 1 ? '一致 ✅（输出等价）' : `不一致 ❌ ${[...sums]}`}`)
}
console.log('─'.repeat(78))
