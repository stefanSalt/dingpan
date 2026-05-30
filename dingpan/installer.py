"""轻量自安装（Windows）。

把当前 exe 复制到 ``%LOCALAPPDATA%\\Dingpan``，并创建开始菜单 / 桌面快捷方式。
免管理员；卸载 = 删该目录 + 删快捷方式。仅 Windows + 打包态有效。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from . import autostart

APP_DIRNAME = "Dingpan"
EXE_NAME = "Dingpan.exe"
SHORTCUT_NAME = "盯盘悬浮窗.lnk"   # 快捷方式显示名（中文无妨，由 PowerShell 以 Unicode 创建）


def is_supported() -> bool:
    return sys.platform.startswith("win") and getattr(sys, "frozen", False)


def install_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, APP_DIRNAME)


def installed_exe() -> str:
    return os.path.join(install_dir(), EXE_NAME)


def is_installed() -> bool:
    return os.path.exists(installed_exe())


def _start_menu_dir() -> str:
    return os.path.join(
        os.environ.get("APPDATA", ""),
        "Microsoft", "Windows", "Start Menu", "Programs",
    )


def _desktop_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _create_shortcut(lnk_path: str, target: str, workdir: str) -> None:
    """用 PowerShell 创建快捷方式（避免引入 pywin32）。

    路径通过环境变量传入，规避 Unicode / 空格 / 引号问题。
    """
    ps = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:DP_LNK);"
        "$s.TargetPath=$env:DP_TGT;$s.WorkingDirectory=$env:DP_WD;$s.Save()"
    )
    env = dict(os.environ, DP_LNK=lnk_path, DP_TGT=target, DP_WD=workdir)
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        env=env,
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def install(desktop: bool = True) -> tuple[bool, str]:
    """执行安装，返回 ``(成功?, 消息)``。"""
    if not is_supported():
        return False, "仅 Windows 打包版支持安装到系统。"

    src = sys.executable
    target = installed_exe()
    try:
        os.makedirs(install_dir(), exist_ok=True)
        if os.path.abspath(src).lower() != os.path.abspath(target).lower():
            shutil.copy2(src, target)
    except OSError as e:
        return False, f"复制程序失败：{e}"

    made: list[str] = []
    try:
        _create_shortcut(os.path.join(_start_menu_dir(), SHORTCUT_NAME), target, install_dir())
        made.append("开始菜单")
    except Exception:
        pass
    if desktop:
        try:
            _create_shortcut(os.path.join(_desktop_dir(), SHORTCUT_NAME), target, install_dir())
            made.append("桌面")
        except Exception:
            pass

    # 若已开启开机自启，把启动项重指到安装后的 exe
    if autostart.is_enabled():
        autostart.enable(autostart.command_for_exe(target))

    where = "、".join(made) if made else "（快捷方式创建失败，可手动从安装目录启动）"
    return True, f"已安装到：{install_dir()}\n已创建快捷方式：{where}"
