#!/usr/bin/env python3
"""
像素基线分区归因：按 UI 区域统计变化像素比。

用途：截图基线对不上时，先分区域量化，再下结论。
     直接归因为「GPU 渲染差异」经常是错的 —— 真凶往往是页脚时钟、
     FPS 计数器、随机 mock 数据这些非确定性来源。

用法：
    python3 pixel-diff-by-region.py <本次捕获.png> <基线.png>
    python3 pixel-diff-by-region.py a.png b.png --threshold 30

判读：
    3D 画布占比极高、footer 干净  → 可能是真实渲染差异（抗锯齿/Bloom/材质）
    footer 占比高                 → 有走秒时钟未冻结（见 SKILL.md 对应小节）
    左侧面板数字变化             → mock 数据漂移（先确认采样时刻一致）

实现说明：纯标准库手写 PNG 解码（zlib + 各类 filter 反算），
          无需 Pillow / numpy，避免在 CI 上引入依赖。
"""
import struct
import sys
import zlib


def read_png(path):
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError(f'{path}: 不是 PNG 文件')
    i, idat, w, h, ct = 8, b'', 0, 0, 0
    while i < len(data):
        ln = struct.unpack('>I', data[i:i + 4])[0]
        typ = data[i + 4:i + 8]
        chunk = data[i + 8:i + 8 + ln]
        if typ == b'IHDR':
            w, h, _bd, ct = struct.unpack('>IIBB', chunk[:10])
        elif typ == b'IDAT':
            idat += chunk
        elif typ == b'IEND':
            break
        i += 12 + ln
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]
    stride = w * ch
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(h):
        f = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        if f == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + (a + prev[x]) // 2) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 255
        out += line
        prev = line
    return w, h, ch, bytes(out)


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    a_path, b_path = sys.argv[1], sys.argv[2]
    threshold = 30
    if '--threshold' in sys.argv:
        threshold = int(sys.argv[sys.argv.index('--threshold') + 1])

    w, h, c, A = read_png(a_path)
    w2, h2, _c2, B = read_png(b_path)
    if (w, h) != (w2, h2):
        print(f'尺寸不同，无法逐像素比较: {w}x{h} vs {w2}x{h2}')
        sys.exit(1)

    # 区域按常见大屏布局切分；width 按比例缩放以适配不同分辨率
    sx = w / 1916.0
    sy = h / 1076.0
    regions = {
        'header': (0, 0, int(1916 * sx), int(90 * sy)),
        '左侧面板': (0, 0, int(380 * sx), h),
        '3D 画布': (int(385 * sx), 0, int(1530 * sx), h),
        '右侧面板': (int(1535 * sx), 0, w, h),
        'footer': (0, int(1030 * sy), w, h),
    }

    total_changed = 0
    print(f'A: {a_path}')
    print(f'B: {b_path}')
    print(f'尺寸: {w}x{h}  变化阈值: 逐通道差 > {threshold}\n')
    print(f'{"区域":<12}{"变化像素":>12}{"总像素":>12}{"比例":>12}')
    print('─' * 50)
    for name, (x0, y0, x1, y1) in regions.items():
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(w, x1), min(h, y1)
        if x1 <= x0 or y1 <= y0:
            continue
        diff = 0
        total = 0
        for y in range(y0, y1):
            base = y * w
            for x in range(x0, x1):
                i = (base + x) * c
                total += 1
                if (abs(A[i] - B[i]) > threshold
                        or abs(A[i + 1] - B[i + 1]) > threshold
                        or abs(A[i + 2] - B[i + 2]) > threshold):
                    diff += 1
        total_changed += diff
        print(f'{name:<12}{diff:>12}{total:>12}{diff / max(total, 1):>12.5f}')

    ratio = total_changed / (w * h)
    print('─' * 50)
    print(f'总计变化比例: {ratio:.6f}')

    if 'footer' in regions:
        fx0, fy0, fx1, fy1 = regions['footer']
        fd = ft = 0
        for y in range(max(0, fy0), min(h, fy1)):
            base = y * w
            for x in range(max(0, fx0), min(w, fx1)):
                i = (base + x) * c
                ft += 1
                if (abs(A[i] - B[i]) > threshold
                        or abs(A[i + 1] - B[i + 1]) > threshold
                        or abs(A[i + 2] - B[i + 2]) > threshold):
                    fd += 1
        if ft and fd / ft > 0.05:
            print('\n⚠️  footer 区域失配偏高 —— 很可能有走秒时钟/FPS 计数器未冻结。')
            print('    这会永久污染基线，应在测试环境下把这些读数钉死。')

    if ratio < 0.001:
        print('\n✅ 失配处于噪声水平，基线稳定。')


if __name__ == '__main__':
    main()
