import subprocess
import os
import io
import glob
import time
import shutil
import hashlib

try:
    from PIL import Image
except ImportError:
    Image = None

LOG_THROTTLE = 300  # 同一类错误最多每 5 分钟打印一次，避免刷屏

_last_log = {}


def log(msg):
    print(msg, flush=True)


def log_throttled(key, msg):
    """限频打印：只在首次或超过 LOG_THROTTLE 秒后输出。"""
    now = time.time()
    if now - _last_log.get(key, 0) >= LOG_THROTTLE:
        _last_log[key] = now
        log(msg)


# --------------------------------------------------------------------------
# 显示 / Xauthority 发现
#
# 本脚本以 systemd --user 服务运行，进程环境里既没有 DISPLAY 也没有
# XAUTHORITY。旧实现直接对 /tmp/.X11-unix/X* 做字典序排序取第一个，会选中
# gdm 登录屏的 :0（属于 gdm 用户，且 cookie 不匹配），导致每一次 xclip 调用
# 都失败；再加上满屏的 `except: pass`，整个桥接会静默空转。
#
# 现在按“权威性”依次尝试，并且每个候选都必须真正探测通过才采用。
# --------------------------------------------------------------------------

def _probe(display, xauthority=None):
    """该 (display, xauthority) 组合是否真的能连上 X server。

    必须用 xdpyinfo 而不是 `xclip -t TARGETS -o`：后者在剪贴板恰好为空时
    也会返回 rc=1（没有属主），会把一个完全正常的显示误判成不可用，
    导致 display 探测飘忽、日志里刷「仍不可用，稍后重试」。
    """
    env = os.environ.copy()
    env['DISPLAY'] = display
    if xauthority:
        env['XAUTHORITY'] = xauthority
    else:
        env.pop('XAUTHORITY', None)
    try:
        if shutil.which('xdpyinfo'):
            r = subprocess.run(['xdpyinfo'], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=8, env=env)
            return r.returncode == 0
        # 退化路径：退而求其次，至少确认 X socket 存在
        return os.path.exists('/tmp/.X11-unix/X' + display.lstrip(':').split('.')[0])
    except Exception:
        return False


def _session_env():
    """systemd 用户管理器里图形会话导出的环境变量（最权威）。"""
    out = {}
    try:
        r = subprocess.run(['systemctl', '--user', 'show-environment'],
                           capture_output=True, text=True, timeout=5)
        for line in r.stdout.splitlines():
            if '=' in line:
                k, v = line.split('=', 1)
                out[k] = v
    except Exception:
        pass
    return out


def _loginctl_displays():
    """当前用户活跃会话上的 X display（xrdp 由会话管理器创建，只能从这里拿到）。"""
    displays = []
    try:
        r = subprocess.run(['loginctl', 'list-sessions', '--no-legend'],
                           capture_output=True, text=True, timeout=5)
        user = os.environ.get('USER') or os.environ.get('LOGNAME')
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) < 6 or parts[2] != user:
                continue
            sid = parts[0]
            if parts[5] != 'active':
                continue
            d = subprocess.run(['loginctl', 'show-session', sid, '-p', 'Display', '--value'],
                               capture_output=True, text=True, timeout=5).stdout.strip()
            if d:
                displays.append(d)
    except Exception:
        pass
    return displays


def _own_sockets():
    """本用户自己拥有的 X socket，跳过 GNOME 设置对话框那种临时 display。"""
    uid = os.getuid()
    setup = (os.environ.get('GNOME_SETUP_DISPLAY') or '').strip()
    setup_num = setup.lstrip(':').split('.')[0]
    found = []
    for path in glob.glob('/tmp/.X11-unix/X*'):
        num = path.rsplit('X', 1)[-1]
        if not num.isdigit():
            continue
        try:
            if os.stat(path).st_uid != uid:   # gdm 的 :0 / :1024 等一律跳过
                continue
        except OSError:
            continue
        if setup_num and num == setup_num:
            continue
        found.append((int(num), ':' + num))
    found.sort()
    return [d for _, d in found]


def detect_display():
    """返回第一个真正可用的 (display, xauthority)，全部失败则回退到环境变量。"""
    home_auth = os.path.expanduser('~/.Xauthority')
    if not os.path.exists(home_auth):
        home_auth = None

    candidates = []

    def add(d, x):
        if d and all(d != c[0] for c in candidates):
            candidates.append((d, x))

    # 1) 进程自身环境
    add(os.environ.get('DISPLAY'), os.environ.get('XAUTHORITY'))
    # 2) systemd 用户管理器导出的图形会话环境
    env = _session_env()
    add(env.get('DISPLAY'), env.get('XAUTHORITY') or home_auth)
    # 3) loginctl 活跃会话（xrdp / 独立 TTY 会话走这条）
    for d in _loginctl_displays():
        add(d, home_auth)
    # 4) 本用户拥有的 X socket
    for d in _own_sockets():
        add(d, home_auth)

    for d, x in candidates:
        if _probe(d, x):
            return d, x

    fallback = os.environ.get('DISPLAY', ':10.0')
    return fallback, os.environ.get('XAUTHORITY')


def apply_display(display, xauthority):
    os.environ['DISPLAY'] = display
    if xauthority:
        os.environ['XAUTHORITY'] = xauthority
    else:
        os.environ.pop('XAUTHORITY', None)


# --------------------------------------------------------------------------
# 剪贴板后端
#
# Wayland 会话走 wl-copy / wl-paste（原生协议，不经过 XWayland 转接，
#   大图也没问题）。
# 纯 X11 会话（xrdp）走 xclip，但 **xclip 持有的 selection 数据接近 1MiB 时
#   会彻底停止应答任何请求**（实测 1,000,002 字节正常、1,048,578 字节起超时）。
#   一旦触发，属主变成"哑巴"，opencode 读取只会等到 1000ms 硬超时并弹
#   "Clipboard read timed out"，桥接自己的 TARGETS 探测也会 10s 超时，
#   于是陷入"重新发布 -> 再次哑巴"的死循环。
#   因此 X11 后端在写入前会把过大的 PNG 压到安全线以下。
# --------------------------------------------------------------------------

X11_SAFE_MAX = 900 * 1024


def detect_backend():
    # 优先 X11/xclip：Wayland 会话下以 1 秒频率轮询 `wl-paste --list-types`
    # 会触发 mutter 的 `meta_window_set_stack_position_no_sync` 断言风暴
    # （窗口每秒被重排 → 画面闪烁、输入法 preedit 被打断/提前提交）。
    # xclip 轮询实测不触发该问题；XWayland 的剪贴板桥接能正常读写。
    #
    # 注意：本函数必须在 detect_display()/apply_display() 之后调用，
    # 这样即使 systemd 用户环境里没有 DISPLAY，也能用探测到的 display。
    if os.environ.get('DISPLAY') and shutil.which('xclip'):
        return 'x11'
    if os.environ.get('WAYLAND_DISPLAY') and shutil.which('wl-copy') and shutil.which('wl-paste'):
        return 'wayland'
    return 'x11'


BACKEND = None


def _fit_x11_limit(target, data):
    """X11 后端写入前把过大的 PNG 压到 xclip 的安全上限以内。"""
    if target != 'image/png' or len(data) <= X11_SAFE_MAX or Image is None:
        return data
    try:
        with Image.open(io.BytesIO(data)) as im:
            im.load()
            w, h = im.size
            for kwargs in ({'optimize': True}, {}):
                buf = io.BytesIO()
                im.save(buf, 'PNG', compress_level=9, **kwargs)
                out = buf.getvalue()
                if len(out) <= X11_SAFE_MAX:
                    print(f"[Bridge] 图片 {len(data)} 字节超出 xclip 安全上限，"
                          f"已压缩到 {len(out)} 字节", flush=True)
                    return out
            for factor in (0.75, 0.5, 0.35, 0.25):
                nw, nh = max(1, int(w * factor)), max(1, int(h * factor))
                buf = io.BytesIO()
                im.resize((nw, nh), Image.LANCZOS).save(buf, 'PNG', compress_level=9, optimize=True)
                out = buf.getvalue()
                if len(out) <= X11_SAFE_MAX:
                    print(f"[Bridge] 图片超出 xclip 安全上限，已降采样至 {nw}x{nh} "
                          f"({len(out)} 字节)", flush=True)
                    return out
    except Exception as exc:
        log_throttled("fit", f"[Bridge] 压缩图片失败 ({type(exc).__name__}: {exc})")
    return data


def get_clipboard_data(target):
    if BACKEND == 'wayland':
        try:
            r = subprocess.run(['wl-paste', '--type', target, '--no-newline'],
                               capture_output=True, timeout=30)
            return r.stdout if r.returncode == 0 else None
        except Exception:
            return None
    try:
        return subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', target, '-o'],
                                     stderr=subprocess.DEVNULL, timeout=30)
    except:
        return None

def set_clipboard_data(target, data):
    if BACKEND == 'wayland':
        try:
            r = subprocess.run(['wl-copy', '--type', target], input=data,
                               capture_output=True, timeout=30)
            return r.returncode == 0
        except Exception:
            return False
    data = _fit_x11_limit(target, data)
    try:
        # 注意：这里不能用 capture_output，否则会一直等后台化的 xclip 释放管道。
        subprocess.run(['xclip', '-selection', 'clipboard', '-t', target, '-i'], input=data,
                       check=True, timeout=30)
        return True
    except:
        return False

def read_targets():
    """返回剪贴板支持的格式列表；读取失败或无属主时返回 None。

    注意：X11 后端这里必须用 subprocess.run 而不是 check_output。剪贴板**无属主**时
    xclip 会以 rc=1 退出（"target TARGETS not available"），check_output 会
    直接抛 CalledProcessError，导致上层走不到自愈分支。而 X11 协议下对无属主的
    selection 发 ConvertSelection 会被服务器丢弃、不回 SelectionNotify，
    opencode 侧只会一直等到 1000ms 硬超时并报 "Clipboard read timed out"。
    """
    if BACKEND == 'wayland':
        try:
            r = subprocess.run(['wl-paste', '--list-types'], capture_output=True, timeout=10)
        except Exception:
            return None
        return r.stdout.decode('utf-8', 'replace').splitlines() if r.returncode == 0 else None
    try:
        r = subprocess.run(['xclip', '-selection', 'clipboard', '-t', 'TARGETS', '-o'],
                           capture_output=True, timeout=10)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return r.stdout.decode('utf-8', 'replace').splitlines()


def republish_last(reason):
    """剪贴板丢失属主时，把上一张图重新发布回去，让 opencode 能立刻读到 image/png。"""
    if last_png is None:
        return False
    if set_clipboard_data('image/png', last_png):
        print(f"[Bridge] {reason}，已重新发布 image/png ({len(last_png)} 字节)", flush=True)
        return True
    log_throttled("republish", f"[Bridge] {reason}，重新发布 image/png 失败")
    return False


def bmp_to_png(raw_data):
    if Image is None:
        return None
    try:
        with Image.open(io.BytesIO(raw_data)) as img:
            png = io.BytesIO()
            img.save(png, 'PNG')
            return png.getvalue()
    except:
        return None

last_bmp_hash = None    # 已经转换并发布过的 image/bmp 内容哈希（防止重复转换/重复抢占）
last_png = None         # 最近一次发布的 PNG 原始数据（剪贴板属主失效后用于自愈）
last_png_hash = None    # 最近一次发布的 PNG 哈希（场景 B 去抖）

display, xauthority = detect_display()
apply_display(display, xauthority)
# 必须在 display 探测/应用之后判定后端：确保 X11 优先，
# 避免服务在 DISPLAY 尚未导出时误选 Wayland 后端（见 detect_backend 注释）。
BACKEND = detect_backend()
print(f"RDP Clipboard Bridge 已启动 (后端={BACKEND}, DISPLAY={display}, "
      f"XAUTHORITY={xauthority or '<默认 ~/.Xauthority>'}, "
      f"PIL={'可用' if Image else '缺失'})", flush=True)

consecutive_failures = 0

while True:
    targets = read_targets()

    if targets is None:
        # 剪贴板无属主 / 读取失败。对无属主的 selection，X 服务器会直接丢弃
        # ConvertSelection 且不回 SelectionNotify，opencode 只能等到 1000ms
        # 硬超时并弹 "Clipboard read timed out"。这里把上一张图重新发布回去。
        consecutive_failures += 1
        republish_last("剪贴板已无属主")
        if consecutive_failures >= 3:
            previous = display
            display, xauthority = detect_display()
            apply_display(display, xauthority)
            consecutive_failures = 0
            if display != previous:
                print(f"[Bridge] 显示已切换: {previous} -> {display} "
                      f"(XAUTHORITY={xauthority or '<默认 ~/.Xauthority>'})", flush=True)
            else:
                print(f"[Bridge] 重新探测显示 {display}（仍不可用，稍后重试）", flush=True)
        time.sleep(1)
        continue

    consecutive_failures = 0

    try:
        # 自愈：属主还在但内容为空时，同样把上一张图放回去
        if not targets:
            republish_last("剪贴板内容为空")
            time.sleep(1)
            continue

        # 文件复制必须原样保留给 RDP 文件传输（gnome-remote-desktop 的 CLIPRDR）。
        # 桥接一旦改写这些格式（历史实现曾把图片文件转成纯 image/png），
        # 桌面/文件管理器复制到 Windows 的文件粘贴就会失效。
        if 'text/uri-list' in targets or 'x-special/gnome-copied-files' in targets:
            time.sleep(1)
            continue

        # 场景 A: RDP 客户端复制的图片 (image/bmp) -> image/png（opencode TUI 等只认 png）
        if 'image/png' not in targets and 'image/bmp' in targets:
            raw_data = get_clipboard_data('image/bmp')
            if raw_data:
                bmp_hash = hashlib.md5(raw_data).hexdigest()
                # 同一张图只做一次昂贵的 BMP 解码，之后直接复用上次的结果。
                # 注意：只要剪贴板还握在 RDP 手里（没有 image/png），就必须重新发布一次，
                # 否则 opencode 读不到 png 会直接报 "X11 clipboard property transfer failed"。
                png_data = last_png if bmp_hash == last_bmp_hash else None
                if png_data is None:
                    png_data = bmp_to_png(raw_data)
                if png_data and set_clipboard_data('image/png', png_data):
                    if bmp_hash != last_bmp_hash:
                        print(f"[Bridge] 已转换 image/bmp -> image/png ({len(png_data)} 字节)", flush=True)
                    last_bmp_hash = bmp_hash
                    last_png = png_data
                    last_png_hash = hashlib.md5(png_data).hexdigest()

        # 场景 B: 发现图片数据 (截图)
        elif 'image/png' in targets:
            raw_data = get_clipboard_data('image/png')
            if raw_data:
                png_hash = hashlib.md5(raw_data).hexdigest()
                if png_hash != last_png_hash:
                    if set_clipboard_data('image/png', raw_data):
                        last_png = raw_data
                        last_png_hash = png_hash
                        last_bmp_hash = None   # 内容来源变了，下次重新判断

        # 注意：这里不再有“把复制的图片文件转成 image/png”的场景。
        # 文件复制（text/uri-list / x-special/gnome-copied-files）必须在
        # 上面的守卫处原样放过，交给 gnome-remote-desktop 的 RDP 文件传输。
    except Exception as exc:
        # 读取/转换过程中出错（display 失效、图像解码失败等）：记录并继续
        log_throttled(
            f"clipboard:{type(exc).__name__}",
            f"[Bridge] 剪贴板处理失败 ({type(exc).__name__}: {exc})")
        if not _probe(display, xauthority):
            previous = display
            display, xauthority = detect_display()
            apply_display(display, xauthority)
            if display != previous:
                print(f"[Bridge] 显示已切换: {previous} -> {display} "
                      f"(XAUTHORITY={xauthority or '<默认 ~/.Xauthority>'})", flush=True)
    time.sleep(1)
