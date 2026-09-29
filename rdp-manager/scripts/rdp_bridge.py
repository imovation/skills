import subprocess
import os
import io
import time
import hashlib
import urllib.parse

try:
    from PIL import Image
except ImportError:
    Image = None

# 自动获取当前环境的 DISPLAY，如果没有则尝试默认值
if 'DISPLAY' not in os.environ:
    os.environ['DISPLAY'] = ':10.0'

def get_clipboard_data(target):
    try:
        return subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', target, '-o'],
                                     stderr=subprocess.DEVNULL, timeout=10)
    except:
        return None

def set_clipboard_data(target, data):
    try:
        subprocess.run(['xclip', '-selection', 'clipboard', '-t', target, '-i'], input=data,
                       check=True, timeout=10)
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

last_hash = ""
print(f"RDP Clipboard Bridge 已启动 (DISPLAY={os.environ['DISPLAY']}, PIL={'可用' if Image else '缺失'})", flush=True)

while True:
    try:
        # 探测当前剪贴板支持的格式
        targets = subprocess.check_output(['xclip', '-selection', 'clipboard', '-t', 'TARGETS', '-o'],
                                        stderr=subprocess.DEVNULL, timeout=10).decode('utf-8').splitlines()

        # 场景 A: RDP 客户端复制的图片 (image/bmp) -> image/png（opencode TUI 等只认 png）
        if 'image/png' not in targets and 'image/bmp' in targets:
            raw_data = get_clipboard_data('image/bmp')
            if raw_data:
                current_hash = hashlib.md5(raw_data).hexdigest()
                if current_hash != last_hash:
                    png_data = bmp_to_png(raw_data)
                    if png_data and set_clipboard_data('image/png', png_data):
                        print(f"[Bridge] 已转换 image/bmp -> image/png ({len(png_data)} 字节)", flush=True)
                        last_hash = hashlib.md5(png_data).hexdigest()

        # 场景 B: 发现图片数据 (截图)
        elif 'image/png' in targets:
            raw_data = get_clipboard_data('image/png')
            if raw_data:
                current_hash = hashlib.md5(raw_data).hexdigest()
                if current_hash != last_hash:
                    set_clipboard_data('image/png', raw_data)
                    last_hash = current_hash

        # 场景 C: 发现文件路径 (复制文件)
        elif 'text/uri-list' in targets:
            uri_data = get_clipboard_data('text/uri-list')
            if uri_data:
                current_hash = hashlib.md5(uri_data).hexdigest()
                if current_hash != last_hash:
                    uri = uri_data.decode('utf-8').strip()
                    if uri.startswith('file://'):
                        path = urllib.parse.unquote(uri[7:])
                        if os.path.exists(path) and path.lower().endswith(('.png', '.jpg', '.jpeg')):
                            with open(path, 'rb') as f:
                                img_data = f.read()
                                mime = 'image/png' if path.lower().endswith('.png') else 'image/jpeg'
                                set_clipboard_data(mime, img_data)
                                last_hash = current_hash
    except:
        pass
    time.sleep(1)
