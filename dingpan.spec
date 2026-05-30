# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件、窗口模式（无控制台）。

本地打包：``pyinstaller --noconfirm dingpan.spec``
CI 同样调用此 spec（见 .github/workflows/build-windows.yml）。
若存在 ``assets/icon.ico`` 则用作 exe 图标，否则用默认图标。
"""

import os

icon = "assets/icon.ico" if os.path.exists("assets/icon.ico") else None
datas = [("assets", "assets")] if os.path.isdir("assets") else []

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="盯盘",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,   # 窗口模式：不弹控制台
    icon=icon,
)
