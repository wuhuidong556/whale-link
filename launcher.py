"""鲸鱼娘 PC 启动器：拉起服务 + 桌面宠物，然后打开页面。

打包成 exe 后双击即用；找不到 Python 时会提示装 Python 3.10+。
"""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

APP = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
PORT = 8770
URL = f"http://127.0.0.1:{PORT}/"


def log(msg):
    with open(os.path.join(APP, "launcher.log"), "a", encoding="utf-8") as f:
        f.write(time.strftime("[%H:%M:%S] ") + msg + "\n")


def good_python(exe):
    """能 import 关键依赖才算可用。"""
    try:
        r = subprocess.run([exe, "-c", "import aiohttp, edge_tts, webview"],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except Exception:
        return False


def find_python():
    cands = [
        os.environ.get("WHALE_PYTHON", ""),
        os.path.join(APP, "runtime", "pythonw.exe"),
        r"D:\Python\pythonw.exe",
        r"C:\Python312\pythonw.exe",
        r"C:\Python311\pythonw.exe",
    ]
    for c in cands:
        if c and os.path.isfile(c) and good_python(c):
            return c
    # PATH 里找
    for name in ("pythonw.exe", "python.exe"):
        for p in os.environ.get("PATH", "").split(os.pathsep):
            f = os.path.join(p, name)
            if os.path.isfile(f) and good_python(f):
                return f
    return None


def healthy():
    try:
        with urllib.request.urlopen(URL + "api/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def start(py, script, cwd):
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    subprocess.Popen([py, script], cwd=cwd, creationflags=flags,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    os.chdir(APP)
    if healthy():
        log("服务已在跑，直接开页面")
        webbrowser.open(URL)
        return

    py = find_python()
    if not py:
        log("找不到 Python")
        print("没找到 Python。请装 Python 3.10+ 并勾选 Add to PATH，或把 pythonw.exe 放到本目录 runtime\\ 下。")
        input("按回车退出…")
        return

    log("使用 " + py)
    server = os.path.join(APP, "server", "app.py")
    if not os.path.isfile(server):
        print("缺少 server/app.py，请把整个文件夹一起拷贝。")
        input("按回车退出…")
        return
    start(py, server, os.path.join(APP, "server"))

    for _ in range(20):
        time.sleep(0.5)
        if healthy():
            break
    else:
        log("服务没起来，看 server 窗口/run.log")
        print("服务没能启动，请查看 launcher.log。")
        input("按回车退出…")
        return

    pet = os.path.join(APP, "pet.py")
    if "--no-pet" not in sys.argv and os.path.isfile(pet):
        start(py, pet, APP)

    webbrowser.open(URL)
    log("已启动")


if __name__ == "__main__":
    main()
