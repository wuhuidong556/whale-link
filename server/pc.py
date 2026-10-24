"""手机能按的电脑按钮。全部走当前用户权限，不做提权。"""
from __future__ import annotations

import ctypes
import os
import subprocess
import tempfile
import webbrowser
from pathlib import Path

user32 = ctypes.windll.user32


def screenshot() -> bytes:
    """截全屏（含多显示器主屏），返回 PNG 字节。"""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "Add-Type -TypeDefinition 'using System;using System.Runtime.InteropServices;"
        "public class D{[DllImport(\"user32.dll\")]public static extern bool SetProcessDPIAware();}';"
        "[D]::SetProcessDPIAware()|Out-Null;"
        "$b=[System.Windows.Forms.Screen]::PrimaryScreen.Bounds;"
        "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($bmp);"
        "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
        "$bmp.Save('%s');$g.Dispose();$bmp.Dispose()" % path.replace("'", "''")
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                   capture_output=True, timeout=20)
    data = Path(path).read_bytes() if Path(path).exists() else b""
    try:
        os.remove(path)
    except OSError:
        pass
    return data


def lock() -> bool:
    return bool(user32.LockWorkStation())


def _key(vk: int, times: int = 1) -> None:
    KEYEVENTF_KEYUP = 0x0002
    for _ in range(times):
        user32.keybd_event(vk, 0, 0, 0)
        user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def volume(delta: int) -> None:
    vk = 0xAF if delta > 0 else 0xAE
    _key(vk, max(1, min(10, abs(delta))))


def media(action: str) -> None:
    table = {"play": 0xB3, "pause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2}
    vk = table.get(action)
    if vk:
        _key(vk)


def open_url(url: str) -> bool:
    if not (url.startswith("http://") or url.startswith("https://")):
        return False
    return bool(webbrowser.open(url))


def power(mode: str) -> bool:
    flags = {"shutdown": "/s", "restart": "/r", "sleep": None}
    if mode == "abort":
        os.system("shutdown /a")
        return True
    if mode == "sleep":
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        return True
    if mode in flags and flags[mode]:
        os.system("shutdown %s /t 30" % flags[mode])
        return True
    return False


def screen_on() -> None:
    """晃一下鼠标，防止屏保把画面吃掉。"""
    try:
        user32.mouse_event(0x0001, 2, 0, 0, 0)
        user32.mouse_event(0x0001, -2, 0, 0, 0)
    except Exception:
        pass


def run_allowed(cmd: str) -> str:
    """只有白名单里的命令能跑，避免变成远程 shell。"""
    allowed = {
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
        "dsh": r"D:\deepseek\DeepSeek Harness.exe",
    }
    exe = allowed.get(cmd.strip().lower())
    if not exe:
        return "不在白名单"
    try:
        subprocess.Popen([exe], close_fds=True)
        return "已启动 " + cmd
    except Exception as e:
        return "失败：" + str(e)[:60]


def wake(mac: str) -> bool:
    """Wake-on-LAN：给同网段的目标机发魔术包。"""
    import socket
    mac = (mac or "").replace(":", "").replace("-", "").strip()
    if len(mac) != 12:
        return False
    try:
        packet = bytes([0xFF]) * 6 + bytes.fromhex(mac) * 16
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, ("255.255.255.255", 9))
        s.close()
        return True
    except Exception:
        return False
