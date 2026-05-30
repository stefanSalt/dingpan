"""检查更新与自动更新（GitHub Releases）。

- 检查：读取 ``https://api.github.com/repos/<repo>/releases/latest`` 比较版本。
- 更新：下载 Release 的 .exe 资产，用「重命名运行中的 exe → 落新文件 → 重启」完成
  就地更新（Windows 允许重命名运行中的 exe，但不允许删除）。
- 仅在「Windows + 已打包成 exe」时才执行替换；其它情况只做检查/引导到下载页。

只用标准库 urllib，不引入额外依赖。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass

from . import __version__

REPO = "stefanSalt/dingpan"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TIMEOUT = 10


@dataclass
class UpdateInfo:
    version: str           # 远端最新版本（去掉前导 v），如 "0.2.1"
    tag: str               # 原始标签，如 "v0.2.1"
    notes: str             # 发布说明
    page_url: str          # Release 网页
    asset_url: str | None  # .exe 直链（可能为空）
    asset_name: str | None


def parse_version(s: str) -> tuple[int, ...]:
    """``'v0.2.10'`` / ``'0.2.10'`` → ``(0, 2, 10)``；无法解析的段记 0。"""
    s = s.strip().lstrip("vV")
    out: list[int] = []
    for part in re.split(r"[.\-+]", s):
        m = re.match(r"\d+", part)
        out.append(int(m.group()) if m else 0)
    return tuple(out) or (0,)


def is_newer(remote: str, local: str) -> bool:
    """``remote`` 版本是否比 ``local`` 新（按段比较，自动补零对齐）。"""
    a, b = parse_version(remote), parse_version(local)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def current_version() -> str:
    return __version__


def is_update_supported() -> bool:
    """是否支持「原地自动更新」：Windows + 已打包 exe。"""
    return sys.platform.startswith("win") and getattr(sys, "frozen", False)


def _pick_exe_asset(assets: list[dict]) -> tuple[str | None, str | None]:
    for a in assets:
        name = a.get("name", "")
        if name.lower().endswith(".exe"):
            return a.get("browser_download_url"), name
    return None, None


def check_for_update() -> UpdateInfo | None:
    """查询最新 Release（无论是否更新都返回，调用方用 :func:`is_newer` 判断）。

    网络 / 解析失败返回 ``None``。
    """
    req = urllib.request.Request(
        API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "dingpan-updater",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None
    tag = data.get("tag_name") or ""
    if not tag:
        return None
    asset_url, asset_name = _pick_exe_asset(data.get("assets", []))
    return UpdateInfo(
        version=tag.lstrip("vV"),
        tag=tag,
        notes=data.get("body") or "",
        page_url=data.get("html_url") or RELEASES_PAGE,
        asset_url=asset_url,
        asset_name=asset_name,
    )


def _download(url: str, dest: str) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": "dingpan-updater"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        return True
    except Exception:
        try:
            if os.path.exists(dest):
                os.remove(dest)
        except OSError:
            pass
        return False


def cleanup_old() -> None:
    """启动时清理上次更新留下的 ``<exe>.old``（best-effort）。"""
    if not getattr(sys, "frozen", False):
        return
    old = sys.executable + ".old"
    try:
        if os.path.exists(old):
            os.remove(old)
    except OSError:
        pass  # 可能仍被占用，下次启动再清


def apply_update(info: UpdateInfo) -> tuple[bool, str]:
    """下载并就地替换、重启。返回 ``(已启动替换?, 消息)``。

    仅 Windows 打包态可用；成功返回后调用方应立即退出应用。
    """
    if not is_update_supported():
        return False, "仅 Windows 打包版支持自动更新。"
    if not info.asset_url:
        return False, "该版本未附带 exe 资产，无法自动更新。"

    cur = sys.executable
    folder = os.path.dirname(cur)
    download = os.path.join(folder, "Dingpan.download.exe")
    old = cur + ".old"

    if not _download(info.asset_url, download):
        return False, "下载失败，请检查网络后重试。"

    try:
        if os.path.exists(old):          # 清理上次残留的备份
            try:
                os.remove(old)
            except OSError:
                pass
        os.replace(cur, old)             # 运行中的 exe 可被重命名
        os.replace(download, cur)        # 新版落到原路径
    except OSError as e:
        try:                             # 回滚
            if not os.path.exists(cur) and os.path.exists(old):
                os.replace(old, cur)
            if os.path.exists(download):
                os.remove(download)
        except OSError:
            pass
        return False, f"替换失败：{e}"

    try:
        subprocess.Popen([cur], close_fds=True)   # 启动新版本（分离进程）
    except OSError as e:
        return False, f"已更新，但自动重启失败：{e}（请手动启动）"
    return True, "更新完成，正在重启…"


def _main() -> None:
    """命令行自检：python -m dingpan.updater"""
    print("当前版本:", current_version(), " 支持原地更新:", is_update_supported())
    info = check_for_update()
    if info is None:
        print("检查失败或无 Release。")
        return
    print(f"最新 Release: {info.tag}  资产: {info.asset_name}")
    print("有新版本！" if is_newer(info.version, current_version()) else "已是最新。")


if __name__ == "__main__":
    _main()
