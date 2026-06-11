"""悬浮窗主体。

特性：无边框 / 置顶 / 半透明 / 圆角，可整窗拖动，右键菜单切换显示模式等。
三种显示模式（简略 / 标准 / 详细）用统一的网格布局重建，值刷新时只改文本与颜色。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QColor, QPainter
from PySide6.QtWidgets import QGridLayout, QLabel, QMenu, QWidget

from . import __version__, catalog
from .config import (
    COLOR_INTL,
    MODE_COMPACT,
    MODE_DETAILED,
    MODE_LABELS,
    MODES,
    Config,
)
from .sina_client import Quote

# ---- 颜色 ----
_RED = "#ff4d4f"      # 红
_GREEN = "#26c281"    # 绿
_FLAT = "#b0b3b8"     # 平/无数据
_NAME = "#e8e8ea"     # 名称文字
_PANEL = QColor(28, 28, 32, 235)  # 圆角面板底色（带透明）


def _colors(scheme: str) -> tuple[str, str]:
    """返回 (涨色, 跌色)。cn=红涨绿跌，intl=绿涨红跌。"""
    return (_GREEN, _RED) if scheme == COLOR_INTL else (_RED, _GREEN)


def _pick(change: float, scheme: str) -> str:
    up, down = _colors(scheme)
    if change > 0:
        return up
    if change < 0:
        return down
    return _FLAT


def _arrow(change: float) -> str:
    return "▲" if change > 0 else "▼" if change < 0 else "—"


def _fmt(v: float, dp: int = 3) -> str:
    """格式化数字：带千分位、最多 dp 位小数并去掉多余的 0。"""
    s = f"{v:,.{dp}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def _short_name(name: str) -> str:
    """简略模式用的短名：取「（」「(」「 」之前的部分。"""
    for sep in ("（", "(", " "):
        if sep in name:
            name = name.split(sep)[0]
            break
    return name[:6]


class FloatingWindow(QWidget):
    """行情悬浮窗。"""

    addRequested = Signal()       # 请求打开「添加品种」
    settingsRequested = Signal()  # 请求打开「设置」
    hideRequested = Signal()      # 请求隐藏到托盘
    checkUpdateRequested = Signal()  # 请求检查更新
    installRequested = Signal()      # 请求安装到系统
    quitRequested = Signal()      # 请求退出

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._quotes: dict[str, Quote] = {}
        self._cells: dict[str, dict[str, QLabel]] = {}
        self._drag_pos = None
        self._stale = False
        self.tray_available = False   # 由主程序按系统托盘可用性设置；决定是否显示「隐藏到托盘」
        self.can_check_update = False  # 由主程序设置：是否显示「检查更新」
        self.can_install = False       # 由主程序设置：是否显示「安装到系统」

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(14, 10, 14, 12)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(5)

        self.apply_config()

        # 初始位置：用配置里记忆的位置，否则放右上角
        if self.config.win_x >= 0 and self.config.win_y >= 0:
            self.move(self.config.win_x, self.config.win_y)
        else:
            self.move(80, 80)

    # ---------- 配置应用 ----------
    def apply_config(self) -> None:
        """（重新）应用窗口标志、不透明度、字体，并重建内容。"""
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.config.always_on_top:
            flags |= Qt.WindowStaysOnTopHint
        was_visible = self.isVisible()
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowOpacity(self.config.opacity)

        f = self.font()
        f.setPointSize(self.config.font_size)
        f.setFamily("Consolas")  # 等宽更整齐；缺失时回退系统默认
        self.setFont(f)

        self.rebuild()
        if was_visible:
            self.show()  # 改 flags 后需重新 show

    # ---------- 布局重建 ----------
    def _clear_grid(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._cells.clear()

    def _label_qss(self, color: str, *, bold: bool = False, size: int | None = None) -> str:
        """构造标签样式。务必把 font-size 写进 QSS——一旦控件设了样式表，
        通过父窗口 setFont 继承来的字号会被 Qt 忽略，否则字号设置看着不生效。"""
        pt = size if size is not None else self.config.font_size
        qss = f"color:{color}; font-family:Consolas; font-size:{pt}pt;"
        if bold:
            qss += " font-weight:600;"
        return qss

    def _make_label(self, text: str = "", *, align_right: bool = False,
                    color: str = _NAME, bold: bool = False,
                    size: int | None = None) -> QLabel:
        lbl = QLabel(text)
        # 鼠标穿透：点在任意标签上都能拖动整个窗口、弹出右键菜单
        lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lbl.setAlignment(
            (Qt.AlignRight if align_right else Qt.AlignLeft) | Qt.AlignVCenter
        )
        lbl.setStyleSheet(self._label_qss(color, bold=bold, size=size))
        return lbl

    def rebuild(self) -> None:
        """按当前显示模式与品种列表重建网格。"""
        self._clear_grid()
        mode = self.config.display_mode
        row = 0
        for code in self.config.symbols:
            cells: dict[str, QLabel] = {}
            if mode == MODE_COMPACT:
                cells["name"] = self._make_label(color=_NAME)
                cells["price"] = self._make_label(align_right=True, bold=True)
                cells["pct"] = self._make_label(align_right=True)
                self._grid.addWidget(cells["name"], row, 0)
                self._grid.addWidget(cells["price"], row, 1)
                self._grid.addWidget(cells["pct"], row, 2)
                row += 1
            else:  # 标准 / 详细 的主行相同
                cells["name"] = self._make_label(color=_NAME)
                cells["price"] = self._make_label(align_right=True, bold=True)
                cells["change"] = self._make_label(align_right=True)
                cells["pct"] = self._make_label(align_right=True)
                self._grid.addWidget(cells["name"], row, 0)
                self._grid.addWidget(cells["price"], row, 1)
                self._grid.addWidget(cells["change"], row, 2)
                self._grid.addWidget(cells["pct"], row, 3)
                row += 1
                if mode == MODE_DETAILED:
                    sub = self._make_label(
                        color=_FLAT, size=max(9, self.config.font_size - 3)
                    )
                    self._grid.addWidget(sub, row, 0, 1, 4)
                    cells["sub"] = sub
                    row += 1
            self._cells[code] = cells

        self._render()      # 把已有数据填回去
        self.adjustSize()   # 自适应大小

    # ---------- 数据刷新 ----------
    def set_quotes(self, quotes: dict[str, Quote], stale: bool = False) -> None:
        """更新行情。``stale=True`` 表示本次取数失败、沿用旧值。"""
        if quotes:
            self._quotes.update(quotes)
        self._stale = stale
        self._render()
        self.update()  # 触发重绘（状态点）

    def _render(self) -> None:
        scheme = self.config.color_scheme
        mode = self.config.display_mode
        for code, cells in self._cells.items():
            q = self._quotes.get(code)
            if q is None:
                # 暂无数据：显示兜底名 + 占位
                cells["name"].setText(
                    _short_name(catalog.fallback_name(code))
                    if mode == MODE_COMPACT else catalog.fallback_name(code)
                )
                for key in ("price", "change", "pct"):
                    if key in cells:
                        cells[key].setText("—")
                        cells[key].setStyleSheet(self._label_qss(_FLAT))
                if "sub" in cells:
                    cells["sub"].setText("")
                continue

            color = _pick(q.change, scheme)
            if mode == MODE_COMPACT:
                cells["name"].setText(_short_name(q.name))
                cells["price"].setText(_fmt(q.price))
                cells["price"].setStyleSheet(self._label_qss(color, bold=True))
                cells["pct"].setText(f"{_arrow(q.change)}{q.change_pct:+.2f}%")
                cells["pct"].setStyleSheet(self._label_qss(color))
            else:
                cells["name"].setText(q.name)
                cells["price"].setText(_fmt(q.price))
                cells["price"].setStyleSheet(self._label_qss(color, bold=True))
                cells["change"].setText(f"{q.change:+.2f}")
                cells["change"].setStyleSheet(self._label_qss(color))
                cells["pct"].setText(f"{_arrow(q.change)}{q.change_pct:+.2f}%")
                cells["pct"].setStyleSheet(self._label_qss(color))
                if "sub" in cells:
                    cells["sub"].setText(
                        f"高 {_fmt(q.high)}   低 {_fmt(q.low)}   "
                        f"昨 {_fmt(q.prev_close)}   {q.time}"
                    )

    # ---------- 绘制：圆角半透明面板 + 状态点 ----------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(_PANEL)
        p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        # 右上角状态点：正常=绿，数据陈旧=橙
        dot = QColor("#f0a020") if self._stale else QColor("#3fae6a")
        p.setBrush(dot)
        p.drawEllipse(self.width() - 12, 6, 5, 5)

    # ---------- 拖动 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            # 优先用系统级移动：Wayland/WSLg 下 move() 无效，这个可用；Windows 也支持
            wh = self.windowHandle()
            if wh is not None:
                try:
                    if wh.startSystemMove():
                        e.accept()
                        return
                except Exception:
                    pass
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._drag_pos is not None:
            self._drag_pos = None
            self.config.save()  # 落盘记忆位置（坐标已在 moveEvent 更新）

    def moveEvent(self, e):
        # 窗口移动后记下坐标（仅改内存，落盘在释放/退出时）
        if self.isVisible():
            self.config.win_x, self.config.win_y = self.x(), self.y()
        super().moveEvent(e)

    # ---------- 右键菜单 ----------
    def contextMenuEvent(self, e):
        menu = QMenu(self)
        header = menu.addAction(f"盯盘悬浮窗 v{__version__}")
        header.setEnabled(False)
        menu.addSeparator()
        mode_menu = menu.addMenu("显示模式")
        group = QActionGroup(mode_menu)
        group.setExclusive(True)
        for m in MODES:
            act = QAction(MODE_LABELS[m], mode_menu, checkable=True)
            act.setChecked(self.config.display_mode == m)
            act.triggered.connect(lambda _checked=False, mm=m: self._set_mode(mm))
            group.addAction(act)
            mode_menu.addAction(act)

        menu.addAction("添加品种…", self.addRequested.emit)
        menu.addAction("设置…", self.settingsRequested.emit)

        if self.can_check_update:
            menu.addAction("检查更新…", self.checkUpdateRequested.emit)
        if self.can_install:
            menu.addAction("安装到系统…", self.installRequested.emit)

        # 仅在有系统托盘时提供「隐藏到托盘」，否则隐藏后无法恢复
        if self.tray_available:
            menu.addAction("隐藏到托盘", self.hideRequested.emit)

        top = QAction("置顶", menu, checkable=True)
        top.setChecked(self.config.always_on_top)
        top.triggered.connect(self._toggle_top)
        menu.addAction(top)

        menu.addSeparator()
        menu.addAction("退出", self.quitRequested.emit)
        menu.exec(e.globalPos())

    def _set_mode(self, mode: str) -> None:
        if mode != self.config.display_mode:
            self.config.display_mode = mode
            self.config.save()
            self.rebuild()

    def _toggle_top(self, checked: bool) -> None:
        self.config.always_on_top = checked
        self.config.save()
        self.apply_config()
