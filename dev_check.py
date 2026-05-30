"""开发自检：数据层烟测 + 品种目录代码校验。

用法（在项目根目录）：.venv/bin/python dev_check.py
不依赖 PySide6，只用到 dingpan.sina_client / catalog。
"""

from dingpan import catalog
from dingpan.sina_client import fetch


def main() -> None:
    print("== 数据层烟测（默认品种）==")
    quotes = fetch(["XAU", "XAG", "CL", "OIL"])
    if not quotes:
        print("  （无数据：可能网络不通）")
    for code in ("XAU", "XAG", "CL", "OIL"):
        q = quotes.get(code)
        if q is None:
            print(f"  {code:<5} 无数据")
            continue
        print(
            f"  {q.name}({q.code}) 现价 {q.price} "
            f"涨跌 {q.change:+.2f} ({q.change_pct:+.2f}%) "
            f"高 {q.high} 低 {q.low} {q.time}"
        )

    print("\n== 品种目录代码校验 ==")
    codes = catalog.all_codes()
    res = fetch(codes)
    ok, bad = [], []
    for c in codes:
        q = res.get(c)
        (ok if q else bad).append((c, q.name) if q else c)
    for c, name in ok:
        print(f"  ✓ {c:<5} {name}")
    print(f"\n  有效 {len(ok)}/{len(codes)}")
    if bad:
        print("  ✗ 无效/无数据：" + " ".join(bad))


if __name__ == "__main__":
    main()
