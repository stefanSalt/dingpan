"""打包 / 启动入口。

以「包」的方式导入 dingpan，保证包内相对导入（from .xxx）在被 PyInstaller
冻结为 exe、或直接运行本文件时都可用——避免
"attempted relative import with no known parent package"。

开发也可继续用：python -m dingpan.main
"""

from dingpan.main import main

if __name__ == "__main__":
    raise SystemExit(main())
