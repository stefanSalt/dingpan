"""开机自启（Windows）。

通过 ``HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
注册表项实现：写入一条指向本程序的启动项即开启，删除该项即关闭。
每用户级、无需管理员权限。仅 Windows 有效；其它平台 :func:`is_supported` 返回 False。
"""

from __future__ import annotations

import os
import sys

try:
    import winreg  # 仅 Windows 提供
except ImportError:                       # 非 Windows（开发机/WSL）
    winreg = None  # type: ignore[assignment]

from .config import _base_dir

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME = "盯盘悬浮窗"                  # 在「任务管理器 > 启动」里显示的名字


def is_supported() -> bool:
    """当前平台是否支持开机自启（仅 Windows）。"""
    return sys.platform.startswith("win") and winreg is not None


def _launch_command() -> str:
    """登录时执行的命令行。"""
    if getattr(sys, "frozen", False):     # 打包后的 exe：直接指向自身
        return f'"{sys.executable}"'
    # 开发态：优先用 pythonw（无控制台）运行 app.py
    py = sys.executable
    pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
    exe = pyw if os.path.exists(pyw) else py
    return f'"{exe}" "{os.path.join(_base_dir(), "app.py")}"'


def is_enabled() -> bool:
    """是否已开启开机自启。"""
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, _VALUE_NAME)
            return bool(value)
    except (FileNotFoundError, OSError):
        return False


def enable() -> bool:
    """写入启动项；成功返回 True。"""
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _launch_command())
        return True
    except OSError:
        return False


def disable() -> bool:
    """删除启动项；成功（或本就不存在）返回 True。"""
    if not is_supported():
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
        return True
    except FileNotFoundError:
        return True                        # 本就没有，视作已关闭
    except OSError:
        return False


def set_enabled(on: bool) -> bool:
    """按开关状态开启/关闭开机自启。"""
    return enable() if on else disable()
