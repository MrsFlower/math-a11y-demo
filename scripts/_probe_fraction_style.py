# -*- coding: utf-8 -*-
"""fraction_style 回归探针：默认档逐字节不变 + compact 档断言。
用法：python scripts/_probe_fraction_style.py
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.parser.python_engine import parse_latex

fails = []


def check(name, got, expected):
    if got != expected:
        fails.append(f"{name}\n  期望：{expected}\n  实际：{got}")
    else:
        print(f"[ok] {name}: {got}")


# 1. 默认档与旧版逐字节一致（含测试用户反馈的那条极限公式）
LIMIT_TEX = r"\lim_{x \to 0}\left(\frac{\sin x}{x}\right)^{\frac{1}{1-\cos x}}"
check(
    "默认档-极限公式",
    parse_latex(LIMIT_TEX)["speech_text"],
    "lim(x→0) 左括号 分数，分子是 sin x，分母是 x，分数结束 右括号 的 "
    "分数，分子是 1，分母是 1 减 cos x，分数结束 次方",
)
check(
    "默认档-简单分式",
    parse_latex(r"\frac{1}{2}")["speech_text"],
    "分数，分子是 1，分母是 2，分数结束",
)

# 2. compact 档：分母 分之 分子；复杂成分报括号
check(
    "compact-简单分式",
    parse_latex(r"\frac{1}{2}", fraction_style="compact")["speech_text"],
    "2 分之 1",
)
check(
    "compact-极限公式",
    parse_latex(LIMIT_TEX, fraction_style="compact")["speech_text"],
    "lim(x→0) 左括号 x 分之 sin x 右括号 的 括号 1 减 cos x 括号 分之 1 次方",
)
check(
    "compact-复杂分子报括号",
    parse_latex(r"\frac{\sqrt{x}+1}{2}", fraction_style="compact")["speech_text"],
    "2 分之 括号 根号下 x，根号结束 加 1 括号",
)

# 3. 导数特例不受 compact 影响（仍读偏导数/导数）
check(
    "compact-偏导特例",
    parse_latex(r"\frac{\partial T}{\partial t}", fraction_style="compact")["speech_text"],
    "T 对 t 的偏导数",
)
check(
    "compact-常导数特例",
    parse_latex(r"\frac{dy}{dx}", fraction_style="compact")["speech_text"],
    "y 对 x 的导数",
)

# 4. 非法值静默回落默认档
check(
    "非法值回落",
    parse_latex(r"\frac{1}{2}", fraction_style="weird")["speech_text"],
    "分数，分子是 1，分母是 2，分数结束",
)

print("-" * 50)
if fails:
    print(f"共 {len(fails)} 条不符：")
    for f in fails:
        print("!!", f)
    sys.exit(1)
print("全部断言通过。")
