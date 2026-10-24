"""双击入口：服务没起就起服务，然后开宠物窗口。"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYW = sys.executable
BASE = "http://127.0.0.1:8770"


def alive() -> bool:
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


if not alive():
    subprocess.Popen([PYW, str(HERE / "server" / "app.py")],
                     cwd=str(HERE / "server"),
                     creationflags=0x08000000)  # CREATE_NO_WINDOW
    for _ in range(40):
        if alive():
            break
        time.sleep(0.25)

os_env = dict()
subprocess.Popen([PYW, str(HERE / "pet.py")], cwd=str(HERE))
