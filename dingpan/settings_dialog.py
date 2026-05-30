"""设置对话框：显示模式、刷新间隔、不透明度、字号、配色、置顶。

点「确定」后写回 :class:`Config` 并保存，再通过 ``changed`` 信号通知主程序应用
（重建窗口、按新间隔重启定时器等）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import QSlider

from .config import (
    COLOR_CN,
    COLOR_INTL,
    MODE_LABELS,
    MODES,
    Config,
)


class SettingsDialog(QDialog):
    """设置。"""

    changed = Signal()

    def __init__(self, config: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("设置")
        self.setMinimumWidth(320)

        form = QFormLayout()

        # 显示模式
        self.mode = QComboBox()
        for m in MODES:
            self.mode.addItem(MODE_LABELS[m], m)
        self.mode.setCurrentIndex(MODES.index(config.display_mode))
        form.addRow("显示模式", self.mode)

        # 刷新间隔
        self.interval = QSpinBox()
        self.interval.setRange(1, 60)
        self.interval.setSuffix(" 秒")
        self.interval.setValue(config.refresh_interval)
        form.addRow("刷新间隔", self.interval)

        # 不透明度（滑块 30~100 ↔ 0.30~1.00）
        opa_row = QHBoxLayout()
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(int(round(config.opacity * 100)))
        self.opacity_lbl = QLabel(f"{self.opacity.value()}%")
        self.opacity.valueChanged.connect(
            lambda v: self.opacity_lbl.setText(f"{v}%")
        )
        opa_row.addWidget(self.opacity, 1)
        opa_row.addWidget(self.opacity_lbl)
        form.addRow("不透明度", opa_row)

        # 字号
        self.font_size = QSpinBox()
        self.font_size.setRange(8, 40)
        self.font_size.setSuffix(" pt")
        self.font_size.setValue(config.font_size)
        form.addRow("字号", self.font_size)

        # 配色
        self.color = QComboBox()
        self.color.addItem("红涨绿跌（A股习惯）", COLOR_CN)
        self.color.addItem("绿涨红跌（国际习惯）", COLOR_INTL)
        self.color.setCurrentIndex(0 if config.color_scheme == COLOR_CN else 1)
        form.addRow("配色", self.color)

        # 置顶
        self.on_top = QCheckBox("窗口始终置顶")
        self.on_top.setChecked(config.always_on_top)
        form.addRow("", self.on_top)

        root = QVBoxLayout(self)
        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _on_ok(self) -> None:
        self.config.display_mode = self.mode.currentData()
        self.config.refresh_interval = self.interval.value()
        self.config.opacity = self.opacity.value() / 100.0
        self.config.font_size = self.font_size.value()
        self.config.color_scheme = self.color.currentData()
        self.config.always_on_top = self.on_top.isChecked()
        self.config.clamp().save()
        self.changed.emit()
        self.accept()
