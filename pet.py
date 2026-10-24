"""桌面宠物：右下角的小窗口，加载 whale-link 的 ?pet=1 页面。

用法：
    pythonw pet.py                 # 正常启动
    PET_OPAQUE=1 pythonw pet.py    # 不透明（排查透明失败时用）
双击「鲸鱼娘.pyw」或桌面快捷方式即可。
"""
import ctypes
import os
import time
import urllib.request
from pathlib import Path

import webview

HERE = Path(__file__).resolve().parent
LOG = HERE / "pet.log"
W, H = 380, 520
BASE = "http://127.0.0.1:8770"


def log(msg: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), msg))


def fatal(msg: str) -> None:
    """失败时弹窗，避免双击一闪而过。"""
    log(msg)
    try:
        ctypes.windll.user32.MessageBoxW(0, msg, "鲸鱼娘没能起来", 0x10)
    except Exception:
        print(msg)


def server_alive() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def screen_size():
    """物理像素尺寸 + DPI 缩放比（pywebview 的 x/y 用逻辑坐标）。"""
    u = ctypes.windll.user32
    u.SetProcessDPIAware()
    sw, sh = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
    try:
        k = u.GetDpiForSystem() / 96.0
    except AttributeError:
        k = 1.0
    return sw, sh, k


def main() -> int:
    if not server_alive():
        fatal("鲸鱼娘服务没在运行（127.0.0.1:8770 连不上）。\n\n"
              "请双击桌面「启动鲸鱼娘」，或先运行 启动鲸鱼娘.vbs。")
        return 1

    tok = ""
    tp = HERE / "data" / "local.txt"
    if tp.exists():
        tok = tp.read_text(encoding="utf-8").strip()
    url = BASE + "/?pet=1" + ("&t=" + tok if tok else "")

    sw, sh, k = screen_size()
    opaque = os.environ.get("PET_OPAQUE") == "1"
    log("start screen=%dx%d dpi=%.2f opaque=%s" % (sw, sh, k, opaque))

    win = webview.create_window(
        "DeepSeek娘", url,
        width=W, height=H,
        x=int((sw - W * k - 24) / k), y=int((sh - H * k - 48) / k),
        frameless=True, easy_drag=True, on_top=True,
        transparent=not opaque,
        background_color="#cfe6f7",
    )
    log("window created")
    webview.start(gui="edgechromium", debug=False)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        import traceback
        fatal("启动出错：\n" + traceback.format_exc()[-1200:])
        raise SystemExit(1)
