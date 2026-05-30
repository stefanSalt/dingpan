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
import threading

from PySide6.QtCore import QObject, Qt, QThread, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QDesktopServices,
    QIcon,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import installer, updater
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
    """跨线程信号中转（主线程 QObject，队列连接自动切回主线程）。"""

    codesChanged = Signal(object)     # 主线程 → 取数线程：品种变化
    intervalChanged = Signal(int)     # 主线程 → 取数线程：间隔变化
    update_checked = Signal(object)   # 更新检查线程 → 主线程：结果(UpdateInfo|None)


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
        self.controller.update_checked.connect(self._on_update_checked)

        # 窗口菜单信号
        self.window.addRequested.connect(self.open_add)
        self.window.settingsRequested.connect(self.open_settings)
        self.window.hideRequested.connect(self._hide_to_tray)
        self.window.checkUpdateRequested.connect(self.check_update_manual)
        self.window.installRequested.connect(self.do_install)
        self.window.quitRequested.connect(self.quit)
        # 菜单项可用性
        self.window.can_check_update = True
        self.window.can_install = installer.is_supported() and not installer.is_installed()
        self._check_manual = False    # 当前检查是否由用户手动触发

        self._add_dialog: AddSymbolDialog | None = None
        self._settings_dialog: SettingsDialog | None = None
        self.tray: QSystemTrayIcon | None = None
        self._build_tray()

        self.thread.start()
        # 启动即最小化到托盘：仅当用户勾选且确有托盘时才不显示窗口
        # （无托盘却隐藏会导致无法唤出，故强制显示）
        if self.config.start_hidden and self.tray is not None:
            self.tray.showMessage(
                "盯盘悬浮窗",
                "已在后台运行，双击托盘图标显示窗口。",
                QSystemTrayIcon.Information,
                3000,
            )
        else:
            self.window.show()
        self.app.aboutToQuit.connect(self._cleanup)

        # 清理上次更新残留 + 启动时后台检查更新
        updater.cleanup_old()
        if self.config.check_update_on_start:
            self._spawn_check(manual=False)

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
        menu.addAction("检查更新…", self.check_update_manual)
        if installer.is_supported() and not installer.is_installed():
            menu.addAction("安装到系统…", self.do_install)
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

    # ---- 检查更新 / 安装 ----
    def check_update_manual(self) -> None:
        """用户手动触发检查更新。"""
        self._spawn_check(manual=True)

    def _spawn_check(self, manual: bool) -> None:
        self._check_manual = manual
        threading.Thread(target=self._do_check, daemon=True).start()

    def _do_check(self) -> None:
        info = updater.check_for_update()            # 后台线程做网络请求
        self.controller.update_checked.emit(info)    # 经队列连接切回主线程

    def _on_update_checked(self, info) -> None:
        manual = self._check_manual
        if info is None:
            if manual:
                QMessageBox.warning(self.window, "检查更新", "检查失败，请稍后重试（或检查网络）。")
            return
        if updater.is_newer(info.version, updater.current_version()):
            self._prompt_update(info)
        elif manual:
            QMessageBox.information(
                self.window, "检查更新", f"已是最新版本（v{updater.current_version()}）。"
            )

    def _prompt_update(self, info) -> None:
        notes = (info.notes or "").strip()
        if len(notes) > 600:
            notes = notes[:600] + "…"
        text = (
            f"发现新版本 {info.tag}（当前 v{updater.current_version()}）。\n\n"
            f"{notes}\n\n是否现在更新？"
        )
        box = QMessageBox(self.window)
        box.setWindowTitle("发现新版本")
        box.setIcon(QMessageBox.Question)
        box.setText(text)
        if updater.is_update_supported() and info.asset_url:
            btn_update = box.addButton("更新并重启", QMessageBox.AcceptRole)
            btn_notes = box.addButton("查看说明", QMessageBox.ActionRole)
            box.addButton("以后再说", QMessageBox.RejectRole)
            box.exec()
            clicked = box.clickedButton()
            if clicked is btn_update:
                self._do_update(info)
            elif clicked is btn_notes:
                self._open_url(info.page_url)
        else:
            # 不支持原地更新（开发态 / 非 Windows）：引导到下载页
            btn_open = box.addButton("打开下载页", QMessageBox.AcceptRole)
            box.addButton("取消", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is btn_open:
                self._open_url(info.page_url)

    def _do_update(self, info) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok, msg = updater.apply_update(info)
        finally:
            QApplication.restoreOverrideCursor()
        if ok:
            self.quit()                  # 新版本已启动，退出当前进程
        else:
            QMessageBox.warning(self.window, "更新", msg)

    def do_install(self) -> None:
        if not installer.is_supported():
            QMessageBox.information(
                self.window, "安装到系统", "仅 Windows 打包版支持安装到系统。"
            )
            return
        ok, msg = installer.install(desktop=True)
        if ok:
            self.window.can_install = False
            QMessageBox.information(
                self.window,
                "安装到系统",
                msg + "\n\n以后可从开始菜单 / 桌面快捷方式启动。",
            )
        else:
            QMessageBox.warning(self.window, "安装到系统", msg)

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

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
