"""树优先转译编排器（第六阶段根治性改造）。

架构分工：
- 纯公式（或 $...$ 等定界符圈出的公式段）走真实语法解析：
  LaTeX --latex2mathml--> MathML 树 --> 中文朗读/紧凑文本。
  语义规则（撇号=导数、点记号=时间导数、向量箭头等）作用在树节点上，
  局部、可测试，不会像正则那样互相干扰。
- 解析失败或输入是图文混排（化学式、单位、题面散文）时返回 None，
  由 transcriber.py 的正则管道兜底——两条路线各守各的边界。

设计铁律沿用第五阶段：宁可少转也不乱转；树路线只处理有真实语法的输入。
"""
from __future__ import annotations

import re

from .parser import python_engine

# 解析前的 Unicode 数学记号归一化：让 latex2mathml 能构建正确的树。
# ′/″ 若直接喂给解析器会被当普通字母（y′′ 变三个 mi，丢失导数结构）；
# 归一成 ASCII 撇号后解析器自动生成 msup(y, ″)，树层再语义化为导数。
_NORMALIZE_PRE = [
    ("\u2033", "''"),   # ″ 双撇号
    ("\u2034", "'''"),  # ‴ 三撇号
    ("\u2032", "'"),    # ′ 单撇号
    ("\u2212", "-"),    # − Unicode 负号
    ("\\,", " "), ("\\;", " "), ("\\!", " "), ("\\ ", " "),  # LaTeX 空白命令
]

# 定界符圈定的数学段（长定界符优先，避免 $ 吞 $$）
_DELIM_RE = re.compile(
    r"\$\$(?P<dd>.+?)\$\$"
    r"|\\\[(?P<sq>.+?)\\\]"
    r"|\\\((?P<ro>.+?)\\\)"
    r"|\$(?P<sd>[^$\n]+?)\$",
    re.S,
)

# 无定界符时判定「像公式」的最低门槛：含 LaTeX 命令/上下标花括号/撇号导数记号。
# 没有这些的输入（如 H2O、Na+、纯散文）一律交回正则管道，避免把普通文本喂给解析器。
_MATH_SMELL = re.compile(r"\\[a-zA-Z]+|[_^]\{|[A-Za-z0-9)\]]['\u2032\u2033\u2034]")

# 视觉大运算符（∫∑∏ 等）与 LaTeX 花括号混写的输入（∫_{-∞}^{∞}f(x)e^(...)dx）：
# 正则管道有专门的上下限/隐式乘法处理，而 latex2mathml 会把 e^( 的圆括号
# 误当上标内容（msup(e, '(')）产生伪结构——这类输入一律交回正则管道。
_VISUAL_BIGOP = re.compile(r"[∫∬∭∮∑∏]")

# 大算子（含上下限）紧凑读法：与正则管道的「积分(从a到b)」惯例对齐
_OP_SPEAK = {"∫": "积分", "∬": "二重积分", "∭": "三重积分", "∮": "环路积分", "∑": "求和", "∏": "连乘"}

# latex2mathml 不认识的记号会原样变成 mi 文本（如 \angle → "angle"），
# 紧凑输出里按正则管道的惯例转回 Unicode 记号
_COMPACT_TEXT_OVERRIDE = {
    "angle": "∠", "triangle": "△", "parallel": "∥", "perpendicular": "⊥",
    "infty": "∞", "circ": "°", "in": "∈", "notin": "∉",
    "cup": "∪", "cap": "∩", "pm": "±", "times": "×", "div": "÷",
}

# 紧凑文本里的 Unicode 上下标映射（复用转译器同款表，保证两条路线观感一致）
_COMPACT_SUB = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
    "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "x": "ₓ", "+": "₊", "-": "₋",
}
_COMPACT_SUP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
    "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "n": "ⁿ",
}


def normalize_pre(tex: str) -> str:
    """解析前归一化：Unicode 撇号/负号/空白命令 → 解析器可识别的形态。"""
    out = tex
    for src, dst in _NORMALIZE_PRE:
        out = out.replace(src, dst)
    return out


def _parse(tex: str) -> dict | None:
    """解析 LaTeX 到结构树；失败返回 None（调用方兜底）。"""
    try:
        return python_engine.parse_latex(normalize_pre(tex.strip()))
    except ValueError:
        return None


def _compact_script(inner: str, table: dict) -> str:
    """上下标内容转 Unicode；任一字符无映射则保留 _{…}/^{…} 形态。"""
    if inner and all(c in table for c in inner.replace(" ", "")):
        return "".join(table.get(c, c) for c in inner if c != " ")
    return inner


def _compact(node: dict) -> str:
    """结构树 → 紧凑 Unicode 文本（unicode_compact 风格，惯例对齐正则管道）。"""
    return _compact_node(node).replace("\u2212", "-")


def _compact_node(node: dict) -> str:
    role = node.get("role")
    kids = node.get("children") or []

    if role == "row" or role == "integral-expr":
        return "".join(_compact_node(c) for c in kids)
    if role == "derivative" and len(kids) == 2:
        # 导数记号在紧凑文本里用规范撇号字符：2 撇合为 ″、3 撇合为 ‴，
        # 读屏逐字念出时与手写记号一致
        primes = len([c for c in kids[1].get("text", "") if c in "\u2032\u2033\u2034"])
        mark = {2: "\u2033", 3: "\u2034"}.get(primes, "\u2032" * max(1, primes))
        return _compact_node(kids[0]) + mark
    if role == "fraction" and len(kids) == 2:
        return f"({_compact_node(kids[0])})/({_compact_node(kids[1])})"
    if role == "sqrt" and kids:
        return f"√({_compact_node(kids[0])})"
    if role == "root" and len(kids) == 2:
        return f"{_compact_node(kids[1])}次√({_compact_node(kids[0])})"
    if role == "bigop" and len(kids) == 3:
        op = _OP_SPEAK.get(kids[0].get("text", ""), kids[0].get("spoken", ""))
        # 括号内不加空格：与正则管道「积分(从a到b)」的紧凑惯例一致
        return f"{op}(从{_compact_node(kids[1])}到{_compact_node(kids[2])}) "
    if role == "superscript" and len(kids) == 2:
        # 上标内部不留空格：树朗读的「2 x」「-iω x」在紧凑文本里应是 2x/-iωx
        inner = _compact_node(kids[1]).replace(" ", "")
        sup = _compact_script(inner, _COMPACT_SUP)
        base = _compact_node(kids[0])
        return base + sup if sup in _COMPACT_SUP.values() or (len(sup) > 0 and sup[0] in "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿ") else f"{base}^({inner})"
    if role == "subscript" and len(kids) == 2:
        inner = _compact_node(kids[1]).replace(" ", "")
        sub = _compact_script(inner, _COMPACT_SUB)
        base = _compact_node(kids[0])
        return base + sub if sub and sub[0] in "₀₁₂₃₄₅₆₇₈₉ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜₓ₊₋" else f"{base}_({inner})"
    if role == "subsup" and len(kids) == 3:
        return f"{_compact_node(kids[0])}_({_compact_node(kids[1])})^({_compact_node(kids[2])})"
    if role == "opscript" and len(kids) == 2:
        return f"{kids[0].get('text', '')}({_compact_node(kids[1])})"
    if role == "accent" and kids:
        return _compact_node(kids[0])
    if role == "matrix":
        # 矩阵紧凑读法沿用正则管道的中文结构（语料基线），借共享入口保证口径一致
        from . import transcriber
        return transcriber.rule_transcribe(node.get("text", ""), profile="unicode_compact")["transcribed_text"]
    text = node.get("text", "")
    if role in ("identifier", "operator"):
        text = _COMPACT_TEXT_OVERRIDE.get(text, text)
    if role == "identifier" and len(text) > 1:
        return text.replace(" ", "")  # sin x 等函数应用去掉树内空格
    return text


def _spoken(node: dict) -> str:
    """结构树 → 结构朗读稿（spoken_structured 风格，直接复用树引擎中文读法）。"""
    from . import transcriber
    return transcriber.add_cjk_spacing(node.get("spoken", ""))


def try_transcribe(text: str, profile: str = "spoken_structured") -> dict | None:
    """树路线转译入口。处理得了返回结果 dict（字段对齐 rule_transcribe），
    处理不了（混排/解析失败/不像公式）返回 None 交回正则管道。

    接管条件刻意收紧，只接管「真公式」输入：
    - 无定界符时必须含结构标记（反斜杠命令/上下标花括号/撇号导数记号）。
      纯视觉 Unicode 公式（∫f(x)dx、求根公式）没有真实语法，解析器只能
      猜，猜错比不转更糟，交回正则管道；
    - 散文包公式的混排（题面、化学式、单位）一律回正则管道；
    - 两档 profile 都接管：紧凑档借 _compact 生成，导数撇号、点记号等
      语义同样需要在紧凑文本里规范化（y'' → y″）。
    """
    stripped = (text or "").strip()
    if not stripped or profile not in ("spoken_structured", "unicode_compact"):
        return None
    # 环境类（cases/bmatrix/array…）正则管道有专门的分段/矩阵读法，
    # latex2mathml 对它们支持很弱，不接管
    if "\\begin{" in stripped:
        return None
    render = _spoken if profile == "spoken_structured" else _compact

    # 情况一：整段恰好被一对定界符完整包住（中间无散文）。多段或段外有字都退回
    m = _DELIM_RE.fullmatch(stripped)
    if m:
        seg = m.group("dd") or m.group("sq") or m.group("ro") or m.group("sd") or ""
        parsed = _parse(seg)
        if parsed is None:
            return None
        return {
            "transcribed_text": render(parsed["tree"]).strip(),
            "applied": ["树形解析-定界符段"],
            "residue": [],
        }

    # 情况二：整段就是公式。门槛：无定界符、无中日韩散文、含结构标记
    # （反斜杠命令/上下标花括号/撇号导数，见 _MATH_SMELL）、无视觉大运算符。
    # 两档 profile 都接管；视觉公式（∫...dx、e^(...)、裸 ^ 无花括号）
    # 没有真实语法，解析器会猜错（把 ^( 的圆括号当上标），交回正则管道。
    if _DELIM_RE.search(stripped):
        return None
    if re.search(r"[\u4e00-\u9fff]", stripped):
        return None
    if not _MATH_SMELL.search(stripped):
        return None
    if _VISUAL_BIGOP.search(stripped):
        return None
    parsed = _parse(stripped)
    if parsed is None:
        return None
    return {"transcribed_text": render(parsed["tree"]), "applied": ["树形解析-整段公式"], "residue": []}
