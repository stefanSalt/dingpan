"""新浪财经行情：获取与解析。

数据源：``https://hq.sinajs.cn/list=<codes>``
- 免费、无需 API key；
- 必须带请求头 ``Referer: https://finance.sina.com.cn``，否则返回 403；
- 响应为 GBK 编码，需 ``decode("gbk")``。

本模块只处理「国际期货/现货」（代码前缀 ``hf_``），字段映射见 :func:`parse_line`。
取数只用标准库 ``urllib``，不引入额外依赖。
"""

from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

API_URL = "https://hq.sinajs.cn/list="
REFERER = "https://finance.sina.com.cn"
PREFIX = "hf_"  # 国际期货/现货前缀
TIMEOUT = 5     # 请求超时（秒）


@dataclass
class Quote:
    """一条行情。

    涨跌以 ``prev_close``（昨收/昨结）为基准计算。
    """

    code: str          # 不带前缀的代码，如 "XAU"
    name: str          # 接口返回的中文名，如 "伦敦金（现货黄金）"
    price: float       # 现价
    prev_close: float  # 昨收/昨结（算涨跌的基准）
    high: float        # 当日最高
    low: float         # 当日最低
    time: str          # 接口给的更新时间，如 "04:55:00"

    @property
    def change(self) -> float:
        """涨跌额。"""
        return self.price - self.prev_close

    @property
    def change_pct(self) -> float:
        """涨跌幅（百分比，已 ×100）。"""
        if not self.prev_close:
            return 0.0
        return (self.price - self.prev_close) / self.prev_close * 100.0


def _has_cjk(s: str) -> bool:
    """字符串是否含中文字符（用于在字段里定位品种名称）。"""
    return any("一" <= ch <= "鿿" for ch in s)


def parse_line(line: str) -> Quote | None:
    """解析一行形如 ``var hq_str_hf_XAU="...";`` 的响应。

    hf_ 字段映射（据真实数据确认）::

        [0] 现价   [4] 最高   [5] 最低   [6] 时间   [7] 昨收/昨结

    名称取「含中文的字段」最稳妥：XAU/XAG 的名称在末尾，而 CL/OIL 末尾
    多了一个成交量字段、名称在倒数第二，故不写死下标，直接扫描含中文的字段。

    解析失败（格式不符 / 现价非法）返回 ``None``。
    """
    line = line.strip()
    if not line.startswith("var ") or "=" not in line:
        return None
    try:
        head, _, rest = line.partition("=")
        var_name = head.split()[-1]              # hq_str_hf_XAU
        if PREFIX not in var_name:
            return None
        code = var_name.split(PREFIX)[-1]         # XAU
        payload = rest.strip().strip(";").strip('"')
        if not payload:
            return None
        parts = payload.split(",")
        if len(parts) < 8:
            return None

        def num(idx: int) -> float:
            try:
                return float(parts[idx])
            except (ValueError, IndexError):
                return 0.0

        price = num(0)
        if price <= 0:                            # 无效/停盘数据
            return None
        name = code
        for field in parts:                       # 扫描含中文的字段作为名称
            if _has_cjk(field):
                name = field.strip()
                break
        return Quote(
            code=code,
            name=name,
            price=price,
            prev_close=num(7),
            high=num(4),
            low=num(5),
            time=parts[6] if len(parts) > 6 else "",
        )
    except Exception:                             # 任何异常都不应让取数崩溃
        return None


def fetch(codes: list[str]) -> dict[str, Quote]:
    """批量获取行情。

    ``codes`` 为不带前缀的代码列表，如 ``["XAU", "CL"]``。
    返回 ``{code: Quote}``；网络或解析失败时对应 code 缺省，
    由调用方决定是否保留上一次的旧值（本函数不抛异常）。
    """
    codes = [c.strip().upper() for c in codes if c.strip()]
    if not codes:
        return {}
    url = API_URL + ",".join(PREFIX + c for c in codes)
    req = urllib.request.Request(
        url,
        headers={"Referer": REFERER, "User-Agent": "Mozilla/5.0"},
    )
    result: dict[str, Quote] = {}
    raw = ""
    for attempt in range(2):                      # 失败重试一次
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                raw = resp.read().decode("gbk", errors="ignore")
            break
        except (urllib.error.URLError, TimeoutError, OSError):
            if attempt == 1:
                return result                     # 整体失败：返回空，调用方保留旧值
    for line in raw.splitlines():
        q = parse_line(line)
        if q is not None:
            result[q.code] = q
    return result


def validate(code: str) -> Quote | None:
    """校验单个代码是否可用，返回其 :class:`Quote`（含接口中文名）或 ``None``。"""
    return fetch([code]).get(code.strip().upper())


def _main() -> None:
    """数据层烟测：``python -m dingpan.sina_client XAU CL``。"""
    import sys

    codes = sys.argv[1:] or ["XAU", "XAG", "CL", "OIL"]
    quotes = fetch(codes)
    if not quotes:
        print("（无数据：可能网络不通或代码均无效）")
        return
    for code in codes:
        q = quotes.get(code.upper())
        if q is None:
            print(f"{code:<6} 无数据/无效")
            continue
        sign = "+" if q.change >= 0 else ""
        print(
            f"{q.name}({q.code})  现价 {q.price}  "
            f"{sign}{q.change:.2f} ({sign}{q.change_pct:.2f}%)  "
            f"高 {q.high} 低 {q.low}  {q.time}"
        )


if __name__ == "__main__":
    _main()
