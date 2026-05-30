"""品种管理对话框。

左侧：内置分组目录（可搜索），双击或点「添加」即用接口实时校验并加入；
右侧：当前已盯品种，可移除、上移/下移调整显示顺序；
底部：手输代码校验添加（适用于目录之外的品种）。

校验通过接口实时进行——能取到名称即有效，并显示接口返回的官方中文名与现价。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import catalog
from .config import Config
from .sina_client import validate

_CODE_ROLE = Qt.UserRole


class AddSymbolDialog(QDialog):
    """品种管理（添加 / 移除 / 排序）。"""

    symbolsChanged = Signal()  # 品种列表变化时通知主程序刷新

    def __init__(self, config: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.config = config
        self.setWindowTitle("品种管理")
        self.resize(560, 460)

        root = QVBoxLayout(self)
        cols = QHBoxLayout()
        root.addLayout(cols, 1)

        # ---- 左：目录 ----
        left = QVBoxLayout()
        cols.addLayout(left, 3)
        left.addWidget(QLabel("可选品种（双击添加）"))
        self.search = QLineEdit(placeholderText="搜索代码或名称…")
        self.search.textChanged.connect(self._filter)
        left.addWidget(self.search)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["代码", "名称"])
        self.tree.setColumnWidth(0, 90)
        self.tree.setRootIsDecorated(True)
        self.tree.itemDoubleClicked.connect(self._on_tree_double)
        left.addWidget(self.tree, 1)
        add_btn = QPushButton("添加选中 →")
        add_btn.clicked.connect(self._add_selected_from_tree)
        left.addWidget(add_btn)

        # ---- 右：已添加 ----
        right = QVBoxLayout()
        cols.addLayout(right, 2)
        right.addWidget(QLabel("已盯品种"))
        self.current = QListWidget()
        self.current.setSelectionMode(QAbstractItemView.SingleSelection)
        right.addWidget(self.current, 1)
        btns = QHBoxLayout()
        for text, slot in (
            ("上移", lambda: self._move(-1)),
            ("下移", lambda: self._move(1)),
            ("移除", self._remove_current),
        ):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        right.addLayout(btns)

        # ---- 底：手输 + 状态 ----
        manual = QHBoxLayout()
        manual.addWidget(QLabel("手输代码:"))
        self.manual_edit = QLineEdit(placeholderText="如 GC、NG、DX（不带 hf_）")
        self.manual_edit.returnPressed.connect(self._add_manual)
        manual.addWidget(self.manual_edit, 1)
        chk = QPushButton("校验并添加")
        chk.clicked.connect(self._add_manual)
        manual.addWidget(chk)
        root.addLayout(manual)

        self.status = QLabel("提示：双击左侧品种，或手输代码后回车。")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

        close = QPushButton("关闭")
        close.clicked.connect(self.accept)
        root.addWidget(close, 0, Qt.AlignRight)

        self._build_tree()
        self._refresh_current()

    # ---------- 目录 ----------
    def _build_tree(self) -> None:
        self.tree.clear()
        for category, items in catalog.CATALOG.items():
            top = QTreeWidgetItem([category, ""])
            top.setFirstColumnSpanned(True)
            for code, name in items:
                child = QTreeWidgetItem([code, name])
                child.setData(0, _CODE_ROLE, code)
                top.addChild(child)
            self.tree.addTopLevelItem(top)
        self.tree.expandAll()
        self._mark_added()

    def _mark_added(self) -> None:
        """已添加的品种在目录里置灰并标注。"""
        current = set(self.config.symbols)
        it = QTreeWidgetItemIterator_leaves(self.tree)
        for leaf in it:
            code = leaf.data(0, _CODE_ROLE)
            added = code in current
            leaf.setDisabled(added)
            base = catalog.fallback_name(code)
            leaf.setText(1, base + "（已添加）" if added else base)

    def _filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            any_visible = False
            for j in range(top.childCount()):
                leaf = top.child(j)
                code = (leaf.data(0, _CODE_ROLE) or "").lower()
                name = leaf.text(1).lower()
                hit = (not text) or (text in code) or (text in name)
                leaf.setHidden(not hit)
                any_visible = any_visible or hit
            top.setHidden(not any_visible)

    def _on_tree_double(self, item, _col):
        code = item.data(0, _CODE_ROLE)
        if code:
            self._try_add(code)

    def _add_selected_from_tree(self):
        item = self.tree.currentItem()
        if item is None:
            self._set_status("请先在左侧选择一个品种。", warn=True)
            return
        code = item.data(0, _CODE_ROLE)
        if not code:
            self._set_status("请选择具体品种（而非分类）。", warn=True)
            return
        self._try_add(code)

    def _add_manual(self):
        self._try_add(self.manual_edit.text())
        self.manual_edit.clear()

    # ---------- 添加（接口校验） ----------
    def _try_add(self, code: str) -> None:
        code = (code or "").strip().upper()
        if not code:
            return
        if code in self.config.symbols:
            self._set_status(f"{code} 已在列表中。", warn=True)
            return
        self._set_status(f"正在校验 {code} …")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            q = validate(code)
        finally:
            QApplication.restoreOverrideCursor()
        if q is None:
            self._set_status(f"❌ {code} 无效或接口暂无数据，未添加。", warn=True)
            return
        self.config.symbols.append(code)
        self.config.save()
        self._set_status(f"✅ 已添加 {q.name}（{code}），现价 {q.price}。")
        self._refresh_current()
        self._mark_added()
        self.symbolsChanged.emit()

    # ---------- 已添加列表 ----------
    def _refresh_current(self) -> None:
        self.current.clear()
        for code in self.config.symbols:
            self.current.addItem(f"{code}    {catalog.fallback_name(code)}")

    def _selected_index(self) -> int:
        row = self.current.currentRow()
        return row if 0 <= row < len(self.config.symbols) else -1

    def _remove_current(self):
        i = self._selected_index()
        if i < 0:
            self._set_status("请先在右侧选择要移除的品种。", warn=True)
            return
        code = self.config.symbols.pop(i)
        self.config.save()
        self._set_status(f"已移除 {code}。")
        self._refresh_current()
        self._mark_added()
        self.symbolsChanged.emit()

    def _move(self, delta: int):
        i = self._selected_index()
        j = i + delta
        if i < 0 or not (0 <= j < len(self.config.symbols)):
            return
        syms = self.config.symbols
        syms[i], syms[j] = syms[j], syms[i]
        self.config.save()
        self._refresh_current()
        self.current.setCurrentRow(j)
        self.symbolsChanged.emit()

    # ---------- 状态栏 ----------
    def _set_status(self, text: str, warn: bool = False) -> None:
        self.status.setStyleSheet("color:#d4380d;" if warn else "color:#389e0d;")
        self.status.setText(text)


def QTreeWidgetItemIterator_leaves(tree: QTreeWidget):
    """遍历所有叶子节点（具体品种）。"""
    for i in range(tree.topLevelItemCount()):
        top = tree.topLevelItem(i)
        for j in range(top.childCount()):
            yield top.child(j)
