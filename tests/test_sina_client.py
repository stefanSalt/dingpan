"""sina_client 解析的离线单元测试。

用真实抓取的样本串断言，不依赖网络。
既可用 ``pytest`` 运行，也可直接 ``python tests/test_sina_client.py`` 运行。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dingpan.sina_client import parse_line  # noqa: E402

# ---- 真实样本（2026-05-30 抓取）----
SAMPLE_XAU = 'var hq_str_hf_XAU="4539.78,4495.590,4539.78,4540.51,4595.01,4489.01,04:55:00,4495.59,4498.19,0,0,0,2026-05-30,伦敦金（现货黄金）";'
SAMPLE_XAG = 'var hq_str_hf_XAG="75.27,75.617,75.27,75.34,76.64,74.58,04:55:00,75.62,75.69,0,0,0,2026-05-30,伦敦银（现货白银）";'
SAMPLE_CL = 'var hq_str_hf_CL="87.861,,87.780,87.810,89.020,86.350,04:59:58,88.900,88.550,0,4,2,2026-05-30,纽约原油,0";'
SAMPLE_OIL = 'var hq_str_hf_OIL="91.985,,91.100,91.910,92.950,89.930,05:55:46,92.700,92.340,0,1,3,2026-05-30,布伦特原油,347866";'


def test_parse_xau():
    q = parse_line(SAMPLE_XAU)
    assert q is not None
    assert q.code == "XAU"
    assert q.name == "伦敦金（现货黄金）"
    assert q.price == 4539.78
    assert q.high == 4595.01
    assert q.low == 4489.01
    assert q.prev_close == 4495.59
    assert q.time == "04:55:00"
    # 涨跌额 / 涨跌幅
    assert abs(q.change - 44.19) < 1e-6
    assert abs(q.change_pct - 0.98296) < 1e-3


def test_parse_cl_with_trailing_volume():
    """CL 末尾多一个成交量字段，名称应取倒数第二个含中文字段。"""
    q = parse_line(SAMPLE_CL)
    assert q is not None
    assert q.code == "CL"
    assert q.name == "纽约原油"          # 不应误取末尾的 "0"
    assert q.price == 87.861
    assert q.high == 89.020
    assert q.low == 86.350
    assert q.prev_close == 88.900
    assert q.time == "04:59:58"
    assert q.change < 0                   # 当日下跌


def test_parse_oil():
    q = parse_line(SAMPLE_OIL)
    assert q is not None
    assert q.code == "OIL"
    assert q.name == "布伦特原油"
    assert q.price == 91.985


def test_parse_xag():
    q = parse_line(SAMPLE_XAG)
    assert q is not None and q.code == "XAG" and q.name == "伦敦银（现货白银）"


def test_parse_invalid():
    assert parse_line("") is None
    assert parse_line("garbage line") is None
    assert parse_line('var hq_str_hf_XAU="";') is None       # 空载荷
    assert parse_line('var hq_str_hf_XYZ="0,,,,,,,,";') is None  # 现价非法


if __name__ == "__main__":
    # 脱离 pytest 直接运行：逐个执行 test_* 并打印结果
    funcs = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in funcs:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ✗ {fn.__name__}: {e}")
    print(f"\n{len(funcs) - failed}/{len(funcs)} 通过")
    sys.exit(1 if failed else 0)
