"""updater 版本比较的离线单元测试（不依赖网络）。

可用 ``pytest`` 运行，也可直接 ``python tests/test_updater.py`` 运行。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dingpan.updater import is_newer, parse_version  # noqa: E402


def test_parse_version():
    assert parse_version("v0.2.10") == (0, 2, 10)
    assert parse_version("0.2.10") == (0, 2, 10)
    assert parse_version("V1.0") == (1, 0)
    assert parse_version("v2") == (2,)
    assert parse_version("1.2.3-beta1") == (1, 2, 3, 0)   # 非数字段记 0


def test_is_newer_basic():
    assert is_newer("0.2.1", "0.2.0")
    assert is_newer("v1.0.0", "0.9.9")
    assert is_newer("0.2.10", "0.2.9")        # 数值比较，非字典序
    assert not is_newer("0.2.0", "0.2.0")     # 相等不算新
    assert not is_newer("0.1.9", "0.2.0")


def test_is_newer_diff_length():
    assert is_newer("0.2.0.1", "0.2.0")       # 多一段补丁号
    assert not is_newer("0.2.0", "0.2.0.1")
    assert not is_newer("1.0", "1.0.0")       # 1.0 == 1.0.0


if __name__ == "__main__":
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
