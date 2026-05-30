"""配置：dataclass + JSON 持久化。

配置文件 ``config.json`` 默认放在程序所在目录（开发时为项目根目录；
打包成 exe 后为 exe 所在目录），首次运行从默认值生成。
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field

# ---- 显示模式 ----
MODE_COMPACT = "compact"     # 简略
MODE_STANDARD = "standard"   # 标准
MODE_DETAILED = "detailed"   # 详细
MODES = (MODE_COMPACT, MODE_STANDARD, MODE_DETAILED)
MODE_LABELS = {MODE_COMPACT: "简略", MODE_STANDARD: "标准", MODE_DETAILED: "详细"}

# ---- 配色方案 ----
COLOR_CN = "cn"      # 红涨绿跌（A 股习惯）
COLOR_INTL = "intl"  # 绿涨红跌（国际习惯）

DEFAULT_SYMBOLS = ["XAU", "XAG", "CL", "OIL"]


def _base_dir() -> str:
    """配置文件所在目录：打包后取 exe 目录，否则取项目根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _config_path() -> str:
    return os.path.join(_base_dir(), "config.json")


@dataclass
class Config:
    """运行配置。字段含义见 ``config.example.json`` 与 README。"""

    symbols: list[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    display_mode: str = MODE_STANDARD
    refresh_interval: int = 3      # 刷新间隔（秒）
    opacity: float = 0.92          # 整体不透明度 0.3~1.0
    font_size: int = 13
    color_scheme: str = COLOR_CN
    always_on_top: bool = True
    start_hidden: bool = False     # 启动时最小化到托盘（需系统托盘）
    win_x: int = -1                # 窗口位置；-1 表示未设置（首次用默认位置）
    win_y: int = -1

    def clamp(self) -> "Config":
        """收敛非法取值，防止配置文件被改坏后崩溃。"""
        if self.display_mode not in MODES:
            self.display_mode = MODE_STANDARD
        if self.color_scheme not in (COLOR_CN, COLOR_INTL):
            self.color_scheme = COLOR_CN
        self.refresh_interval = max(1, min(60, int(self.refresh_interval)))
        self.opacity = max(0.3, min(1.0, float(self.opacity)))
        self.font_size = max(8, min(40, int(self.font_size)))
        # 去重并大写品种代码
        seen, cleaned = set(), []
        for s in self.symbols:
            s = str(s).strip().upper()
            if s and s not in seen:
                seen.add(s)
                cleaned.append(s)
        self.symbols = cleaned or list(DEFAULT_SYMBOLS)
        return self

    def save(self, path: str | None = None) -> None:
        path = path or _config_path()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # 配置写入失败不应影响运行

    @classmethod
    def load(cls, path: str | None = None) -> "Config":
        path = path or _config_path()
        if not os.path.exists(path):
            cfg = cls()
            cfg.save(path)
            return cfg
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return cls()
        # 仅取已知字段，向后兼容旧配置
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known).clamp()
