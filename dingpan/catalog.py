"""内置品种目录（国际期货/现货，前缀 ``hf_``），按类别分组，供「添加品种」浏览。

说明：新浪没有「列出全部品种」的官方接口，这里维护一份常用代码清单；
实际添加时由 :func:`dingpan.sina_client.validate` 实时校验并取接口中文名，
因此即便个别代码失效，也只会在添加界面被标记为不可用，不影响已有功能。

下面每项为 ``(代码, 备注名)``，代码不带 ``hf_`` 前缀；备注名仅作离线兜底显示，
真实名称以接口返回为准。
"""

from __future__ import annotations

# {类别: [(代码, 备注名), ...]}
# 备注名已据接口实测校准（2026-05-30）；运行时仍以接口返回的名称为准。
CATALOG: dict[str, list[tuple[str, str]]] = {
    "贵金属": [
        ("XAU", "伦敦金（现货黄金）"),
        ("XAG", "伦敦银（现货白银）"),
        ("GC", "纽约黄金"),
        ("SI", "纽约白银"),
        ("HG", "美铜"),
    ],
    "能源": [
        ("CL", "纽约原油 (WTI)"),
        ("OIL", "布伦特原油"),
        ("NG", "美国天然气"),
        ("HO", "美燃油"),
    ],
    "农产品": [
        ("S", "美国大豆"),
        ("C", "美国玉米"),
        ("W", "美国小麦"),
        ("BO", "美黄豆油"),
        ("SM", "美黄豆粉"),
        ("CT", "美国棉花"),
        ("KC", "美国咖啡"),
        ("CC", "可可"),
    ],
}

# 注：外汇 / 指数（美元指数、欧元、日元等）在 hf_ 前缀下取不到数据——
# 新浪外汇用的是另一套前缀与字段格式（如 fx_）。本期只支持 hf_，留作后续扩展。
# 手输其它 hf_ 代码时，「品种管理」会实时校验，有效才会加入，不必担心写错。


def all_codes() -> list[str]:
    """目录中所有代码（去前缀）。"""
    return [code for items in CATALOG.values() for code, _ in items]


def fallback_name(code: str) -> str:
    """按代码取离线兜底名称；找不到则返回代码本身。"""
    code = code.upper()
    for items in CATALOG.values():
        for c, name in items:
            if c == code:
                return name
    return code
