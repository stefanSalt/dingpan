"""程序入口。

职责：
- 创建 ``QApplication``、悬浮窗、系统托盘；
- 在后台线程里用 ``QTimer`` 周期取数，经信号回主线程刷新 UI（不阻塞界面）；
- 串联「添加品种」「设置」对话框与配置。

运行：``python -m dingpan.main``
"""

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .add_symbol_dialog import AddSymbolDialog
from .config import MODE_LABELS, MODES, Config, _base_dir
from .floating_window import FloatingWindow
from .settings_dialog import SettingsDialog
from .sina_client import fetch


# ---------------- 后台取数 ----------------
class Fetcher(QObject):
    """在后台线程周期性拉取行情。

    ``quotesReady`` 第二个参数 ``stale=True`` 表示本次整体取数失败（沿用旧值）。
    """

    quotesReady = Signal(object, bool)

    def __init__(self, codes: list[str], interval: int):
        super().__init__()
        self._codes = list(codes)
        self._interval = max(1, interval)
        self._timer: QTimer | None = None

    @Slot()
    def start(self) -> None:
        """在所属线程启动后创建定时器（保证定时器属于该线程）。"""
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(self._interval * 1000)
        self._tick()  # 立即取一次

    def _tick(self) -> None:
        quotes = fetch(self._codes)
        stale = bool(self._codes) and not quotes
        self.quotesReady.emit(quotes, stale)

    @Slot(object)
    def set_codes(self, codes) -> None:
        self._codes = list(codes)
        self._tick()  # 品种变化立即刷新

    @Slot(int)
    def set_interval(self, seconds: int) -> None:
        self._interval = max(1, int(seconds))
        if self._timer is not None:
            self._timer.setInterval(self._interval * 1000)


class _Controller(QObject):
    """主线程 → 后台线程的控制信号（跨线程自动走队列连接）。"""

    codesChanged = Signal(object)
    intervalChanged = Signal(int)


def _make_icon() -> QIcon:
    """托盘/窗口图标：优先用 assets 下的图标文件，否则程序内画一个。"""
    search_dirs = []
    if getattr(sys, "_MEIPASS", None):       # PyInstaller 单文件解包目录
        search_dirs.append(sys._MEIPASS)
    search_dirs.append(_base_dir())
    for d in search_dirs:
        for fn in ("assets/icon.ico", "assets/icon.png"):
            path = os.path.join(d, fn)
            if os.path.exists(path):
                return QIcon(path)
    pix = QPixmap(32, 32)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#1f1f28"))
    p.drawRoundedRect(0, 0, 32, 32, 7, 7)
    p.setBrush(QColor("#f0a020"))
    p.drawEllipse(8, 8, 16, 16)
    p.end()
    return QIcon(pix)


# ---------------- 应用 ----------------
class DingpanApp:
    """组装窗口、托盘、后台线程与对话框。"""

    def __init__(self, app: QApplication):
        self.app = app
        self.config = Config.load()
        self.window = FloatingWindow(self.config)

        # 后台取数线程
        self.controller = _Controller()
        self.thread = QThread()
        self.fetcher = Fetcher(self.config.symbols, self.config.refresh_interval)
        self.fetcher.moveToThread(self.thread)
        self.thread.started.connect(self.fetcher.start)
        self.fetcher.quotesReady.connect(self.window.set_quotes)
        self.controller.codesChanged.connect(self.fetcher.set_codes)
        self.controller.intervalChanged.connect(self.fetcher.set_interval)

        # 窗口菜单信号
        self.window.addRequested.connect(self.open_add)
        self.window.settingsRequested.connect(self.open_settings)
        self.window.hideRequested.connect(self._hide_to_tray)
        self.window.quitRequested.connect(self.quit)

        self._add_dialog: AddSymbolDialog | None = None
        self._settings_dialog: SettingsDialog | None = None
        self.tray: QSystemTrayIcon | None = None
        self._build_tray()

        self.thread.start()
        self.window.show()
        self.app.aboutToQuit.connect(self._cleanup)

    # ---- 托盘 ----
    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            # 无托盘环境（部分 WSLg）：仍可用窗口右键菜单控制
            print("（提示：当前环境无系统托盘，用窗口右键菜单操作。）")
            return
        self.tray = QSystemTrayIcon(_make_icon(), self.app)
        self.tray.setToolTip("盯盘悬浮窗")
        menu = QMenu()
        menu.addAction("显示 / 隐藏", self.toggle_show)

        mode_menu = menu.addMenu("显示模式")
        group = QActionGroup(mode_menu)
        group.setExclusive(True)
        for m in MODES:
            act = QAction(MODE_LABELS[m], mode_menu, checkable=True)
            act.setChecked(self.config.display_mode == m)
            act.triggered.connect(lambda _c=False, mm=m: self.set_mode(mm))
            group.addAction(act)
            mode_menu.addAction(act)
        self._mode_group = group  # 保留引用

        menu.addAction("添加品种…", self.open_add)
        menu.addAction("设置…", self.open_settings)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()
        self.window.tray_available = True   # 让窗口右键菜单显示「隐藏到托盘」

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_show()

    # ---- 动作 ----
    def toggle_show(self) -> None:
        if self.window.isVisible():
            self.window.hide()
        else:
            self.window.show()
            self.window.raise_()

    def _hide_to_tray(self) -> None:
        """隐藏悬浮窗到托盘，并提示恢复方式。"""
        self.window.hide()
        if self.tray is not None:
            self.tray.showMessage(
                "盯盘悬浮窗",
                "已隐藏到托盘，双击托盘图标可恢复显示。",
                QSystemTrayIcon.Information,
                3000,
            )

    def set_mode(self, mode: str) -> None:
        if mode != self.config.display_mode:
            self.config.display_mode = mode
            self.config.save()
            self.window.rebuild()

    def open_add(self) -> None:
        dlg = AddSymbolDialog(self.config, self.window)
        dlg.symbolsChanged.connect(self._on_symbols_changed)
        self._add_dialog = dlg
        dlg.exec()

    def _on_symbols_changed(self) -> None:
        self.window.rebuild()
        self.controller.codesChanged.emit(list(self.config.symbols))

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.window)
        dlg.changed.connect(self._on_settings_changed)
        self._settings_dialog = dlg
        dlg.exec()

    def _on_settings_changed(self) -> None:
        self.window.apply_config()
        self.controller.intervalChanged.emit(self.config.refresh_interval)
        # 同步托盘里显示模式的勾选
        if self.tray is not None:
            for act in self._mode_group.actions():
                act.setChecked(MODE_LABELS[self.config.display_mode] == act.text())

    def quit(self) -> None:
        self.app.quit()

    def _cleanup(self) -> None:
        self.config.save()  # 持久化最终窗口位置等
        if self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2000)
        if self.tray is not None:
            self.tray.hide()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("盯盘悬浮窗")
    app.setQuitOnLastWindowClosed(False)  # 关窗不退出，托盘/右键菜单常驻
    _app = DingpanApp(app)  # 持有引用，避免被回收
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
