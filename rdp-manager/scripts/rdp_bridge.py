import subprocess
import os
import io
import glob
import time
import hashlib
import urllib.parse

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
    """该 (display, xauthority) 组合是否真的能连上 X server。"""
    env = os.environ.copy()
    env['DISPLAY'] = display
    if xauthority:
        env['XAUTHORITY'] = xauthority
    else:
        env.pop('XAUTHORITY', None)
    try:
        r = subprocess.run(['xclip', '-selection', 'clipboard', '-t', 'TARGETS', '-o'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=5, env=env)
        return r.returncode == 0
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


def get_clipboard_data(target):
    try:
        return subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', target, '-o'],
                                     stderr=subprocess.DEVNULL, timeout=30)
    except:
        return None

def set_clipboard_data(target, data):
    try:
        subprocess.run(['xclip', '-selection', 'clipboard', '-t', target, '-i'], input=data,
                       check=True, timeout=30)
        return True
    except:
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
print(f"RDP Clipboard Bridge 已启动 (DISPLAY={display}, "
      f"XAUTHORITY={xauthority or '<默认 ~/.Xauthority>'}, "
      f"PIL={'可用' if Image else '缺失'})", flush=True)

consecutive_failures = 0

while True:
    try:
        # 探测当前剪贴板支持的格式
        targets = subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', 'TARGETS', '-o'],
                                        stderr=subprocess.DEVNULL, timeout=10).decode('utf-8').splitlines()
        consecutive_failures = 0

        # 自愈：剪贴板没有任何属主（xclip 进程被杀 / 属主异常退出）时，
        # opencode 的原生读取会一直等不到 ConvertSelection 回应而报
        # "Clipboard read timed out"。这里把上一张图重新发布回去。
        if not targets:
            if last_png is not None:
                if set_clipboard_data('image/png', last_png):
                    print(f"[Bridge] 剪贴板属主已失效，已重新发布 image/png "
                          f"({len(last_png)} 字节)", flush=True)
                else:
                    log_throttled("republish", "[Bridge] 重新发布 image/png 失败")
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

        # 场景 C: 发现文件路径 (复制文件)
        elif 'text/uri-list' in targets:
            uri_data = get_clipboard_data('text/uri-list')
            if uri_data:
                current_hash = hashlib.md5(uri_data).hexdigest()
                if current_hash != last_png_hash:
                    uri = uri_data.decode('utf-8').strip()
                    if uri.startswith('file://'):
                        path = urllib.parse.unquote(uri[7:])
                        if os.path.exists(path) and path.lower().endswith(('.png', '.jpg', '.jpeg')):
                            with open(path, 'rb') as f:
                                img_data = f.read()
                                mime = 'image/png' if path.lower().endswith('.png') else 'image/jpeg'
                                if set_clipboard_data(mime, img_data):
                                    last_png_hash = current_hash
                                    last_bmp_hash = None
    except Exception as exc:
        # display 失效（注销、xrdp 重连、重启）时重新发现一次
        consecutive_failures += 1
        log_throttled(
            f"clipboard:{consecutive_failures}",
            f"[Bridge] 剪贴板读取失败 ({type(exc).__name__}: {exc})，连续 {consecutive_failures} 次")
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
