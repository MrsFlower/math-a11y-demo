"""第五阶段：理科符号转译（转译模式规则引擎）。

定位：把读屏读不了的数学/物理/化学符号转成 Unicode 纯文本，
不解释、不客套、不改语义、尽量不动原文结构。规则来自真实视障用户
（北辰）的 Accessibility Protocol 提示词清单。

设计铁律（与讲解模式相反）：
- 只做确定性替换，命中的 token 转换，其余原文一字不动；
- 宁可少转也不乱转：拿不准的交给 LLM 路线或留在 warnings 里，绝不胡编；
- applied 列表记录命中了哪些规则，可测试、可解释。
"""
from __future__ import annotations

import re

# Unicode 下标/上标字符表（仅收常见字符，表外字符保留原样并触发 LLM/警告）
_SUB_MAP = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "₅",
    "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
    "l": "ₗ", "m": "ₘ", "n": "ₙ", "o": "ₒ", "p": "ₚ", "r": "ᵣ",
    "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
}
_SUP_MAP = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵",
    "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ",
    "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ", "k": "ᵏ", "l": "ˡ",
    "m": "ᵐ", "n": "ⁿ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ",
    "t": "ᵗ", "u": "ᵘ", "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

_GREEK_SPOKEN = {
    "α": "阿尔法", "β": "贝塔", "γ": "伽马", "δ": "德尔塔", "Δ": "德尔塔",
    "θ": "西塔", "λ": "兰姆达", "μ": "缪", "ρ": "柔", "σ": "西格玛",
    "ω": "欧米伽", "Ω": "欧姆",
}

# ---------- LaTeX 命令规则 ----------

def _latex_frac(m: re.Match) -> str:
    return f"({m.group(1)})/({m.group(2)})"


def _latex_int(m: re.Match) -> str:
    lo, hi = m.group(1), m.group(2)
    return f"积分(从{lo}到{hi}) "


def _latex_lim(m: re.Match) -> str:
    return f"lim({m.group(1)}→{m.group(2)})"


def _sup_inner(inner: str) -> str:
    """上标内容整体转 Unicode；复杂内容按协议保留 ^(...)。"""
    inner = inner.replace("−", "-").strip()
    if len(inner) == 1 and inner in _SUP_MAP:
        return _SUP_MAP[inner]
    return "^(" + inner + ")"


# (模式名, 正则, 替换) —— 顺序有意义：先结构化命令，后记号级替换
_LATEX_RULES: list[tuple[str, re.Pattern, str | object]] = [
    ("LaTeX空白", re.compile(r"\\[,;!]\s*|\\\s+"), " "),
    ("LaTeX分式", re.compile(r"\\[dD]?frac\{([^{}]*)\}\{([^{}]*)\}"), _latex_frac),
    ("LaTeX多次根号", re.compile(r"\\sqrt\[([^\]]*)\]\{([^{}]*)\}"), lambda m: f"{m.group(1)}次√({m.group(2)})"),
    ("LaTeX根号", re.compile(r"\\sqrt\{([^{}]*)\}"), lambda m: f"√({m.group(1)})"),
    ("LaTeX定积分", re.compile(r"\\int_\{?([^{}\s]+)\}?\^\{?([^{}\s]+)\}?\s*"), _latex_int),
    ("LaTeX极限", re.compile(r"\\lim_\{?([^{}\s]+)\}?\s*(?:\\to|\\rightarrow)\s*"), _latex_lim),
    ("LaTeX无穷", re.compile(r"\\infty\s*"), "∞"),
    ("LaTeX不属于", re.compile(r"\\notin\s*"), "∉"),
    ("LaTeX指数", re.compile(r"(?<=[\w)\]])\^\{([^{}]*)\}"), lambda m: _sup_inner(m.group(1))),
    ("LaTeX角", re.compile(r"\\angle\s*"), "∠"),
    ("LaTeX三角形", re.compile(r"\\triangle\s*"), "△"),
    ("LaTeX平行", re.compile(r"\\parallel\s*"), "∥"),
    ("LaTeX垂直", re.compile(r"\\perp\s*"), "⊥"),
    ("LaTeX属于", re.compile(r"\\in\s*"), "∈"),
    ("LaTeX包含于", re.compile(r"\\subseteq\s*"), "⊆"),
    ("LaTeX交", re.compile(r"\\cap\s*"), "∩"),
    ("LaTeX并", re.compile(r"\\cup\s*"), "∪"),
    ("LaTeX圆周率", re.compile(r"\\pi\s*"), "π"),
    ("LaTeX角度", re.compile(r"\\circ\s*"), "°"),
    ("LaTeX正负", re.compile(r"\\pm\s*"), "±"),
    ("LaTeX希腊字母", re.compile(r"\\(alpha|beta|gamma|theta|lambda|mu|rho|sigma|omega)\b"),
     lambda m: {"alpha": "α", "beta": "β", "gamma": "γ", "theta": "θ",
                "lambda": "λ", "mu": "μ", "rho": "ρ", "sigma": "σ", "omega": "ω"}[m.group(1)]),
    ("LaTeX乘号", re.compile(r"\\times\s*"), "×"),
    ("LaTeX除号", re.compile(r"\\div\s*"), "÷"),
    ("LaTeX小于等于", re.compile(r"\\leq?\s*"), "≤"),
    ("LaTeX大于等于", re.compile(r"\\geq?\s*"), "≥"),
    ("LaTeX不等于", re.compile(r"\\neq?\s*"), "≠"),
    ("LaTeX箭头", re.compile(r"\\to\s*|\\rightarrow\s*"), "→"),
    ("LaTeX可逆反应", re.compile(r"\\rightleftharpoons\s*"), "⇌"),
]

# ---------- 普通文本记号规则 ----------

_PLAIN_RULES: list[tuple[str, re.Pattern, str | object]] = [
    ("Unicode负号", re.compile(r"−"), "-"),
    ("视觉定积分", re.compile(r"∫_\{?([^{}\s]+)\}?\^\{?([^{}\s]+)\}?\s*"), _latex_int),
    # 离子必须在化学式之前：否则 SO4^2- 会被化学式规则先改成 SO₄，电荷就拼不上了
    # 离子：Na+ / Cu2+（元素后电荷），SO4^2- / SO4 2-（原子团电荷）
    ("原子团电荷",
     re.compile(r"([A-Z][A-Za-z0-9]*?)\s?\^\s?(\d*)([+-])(?=\s|$|[，。、）)])"),
     lambda m: _ion_poly(m)),
    # 空格变体 SO4 2-：要求原子团含数字且电荷至少一位，避免误伤「AB + CD」这类表达式
    ("原子团电荷空格变体",
     re.compile(r"([A-Z][A-Za-z]*\d[A-Za-z0-9]*)\s(\d+)([+-])(?=\s|$|[，。、）)])"),
     lambda m: _ion_poly(m)),
    ("离子电荷",
     re.compile(r"\b([A-Z][a-z]?)(\d*)([+-])(?=\s|$|[，。、）)])"),
     lambda m: _ion_simple(m)),
    # 化学式：分子级扫描，元素字母后的数字转 Unicode 下标（H2O/CO2/H2SO4）。
    # 数字可出现在任意元素后（CO2 的 C 无数字），整体必须含数字才转；
    # 前置只拦字母。代价：MP3/iPhone15 这类「字母+数字」词也会被下标化——
    # 转译场景以理科材料为主，可接受（宁可误转这类罕见词，不漏 CO2 这类高频式）。
    ("化学式下标",
     re.compile(r"(?<![A-Za-z])(?:[A-Z][a-z]?\d*)+(?![a-z])"),
     lambda m: _chem_formula(m)),
    # 根号：sqrt(3x+1) -> √(3x+1)，sqrt3 -> √3
    ("根号", re.compile(r"\bsqrt\s*\(([^()]*)\)"), lambda m: f"√({m.group(1)})"),
    ("根号无括号", re.compile(r"\bsqrt(\d+(?:\.\d+)?)\b"), lambda m: f"√{m.group(1)}"),
    # 上标：x^2 -> x²，(x+1)^2 -> (x+1)²；括号结尾也允许；
    # 仅单字符指数转 Unicode，复杂指数 2^(n-1) 按协议保留原样
    ("上标", re.compile(r"(?<=[\w)\]])\^([0-9a-zA-Z])"), lambda m: _sup_single(m)),
    ("指数括号规整", re.compile(r"(?<=[\w)\]])\^\(([^()]*)\)"), lambda m: _sup_inner(m.group(1))),
    # 下标：a_1 -> a₁，a_{n+1} -> aₙ₊₁；log_2 -> log₂。
    # 限制：下划线前必须是「独立单字母/函数名」（前面不能再是字母数字），
    # 否则 user_name 这类普通下划线命名会被误转——宁可少转不乱转。
    ("对数底数", re.compile(r"\blog_([0-9a-z])"), lambda m: "log" + _SUB_MAP.get(m.group(1), "_" + m.group(1))),
    ("对数底数花括号", re.compile(r"\blog_\{([^{}]*)\}"), lambda m: "log" + _sub_inner(m.group(1))),
    ("花括号下标", re.compile(r"(?<![A-Za-z0-9_])([A-Za-z])_\{([^{}]*)\}"),
     lambda m: m.group(1) + _sub_inner(m.group(2))),
    ("下标", re.compile(r"(?<![A-Za-z0-9_])([A-Za-z])_([0-9a-z])"),
     lambda m: m.group(1) + _SUB_MAP.get(m.group(2), "_" + m.group(2))),
    # 关系与集合记号
    ("小于等于", re.compile(r"<="), "≤"),
    ("大于等于", re.compile(r">="), "≥"),
    ("不等于", re.compile(r"!="), "≠"),
    ("正负号", re.compile(r"\+/-|\+\\-|±"), "±"),
    ("无穷", re.compile(r"\binfinity\b|\+inf\b"), "∞"),
    ("属于", re.compile(r"(?<=\s)in(?=\s+[A-Z{])"), "∈"),
    ("平行", re.compile(r"\bparallel\b"), "∥"),
    ("垂直", re.compile(r"\bperpendicular\b"), "⊥"),
    ("角", re.compile(r"\bangle\s+"), "∠"),
    ("三角形", re.compile(r"\btriangle\s+"), "△"),
    ("极限", re.compile(r"\blim\s+(?:\(?)\s*([a-zA-Z]\w*)\s*(?:->|→)\s*([^)\s,，]+)\s*(?:\)?)(?=\s)"),
     lambda m: f"lim({m.group(1)}→{m.group(2)})"),
    # 度数：30°C / 30 ℃ 归一；裸 "30 C" 不转（可能是其他缩写），只加空格提示
    ("摄氏度", re.compile(r"(\d+)\s*°\s*[Cc]\b"), lambda m: f"{m.group(1)}℃"),
    # Delta 拼写 -> Δ（仅后接字母时，避免误伤地名）
    ("变化量Δ", re.compile(r"\b[Dd]elta\s+([A-Za-z])"), lambda m: f"Δ{m.group(1)}"),
    ("裸积分符", re.compile(r"∫"), "积分"),
    ("隐式乘法", re.compile(r"(?<=\))(?=(?!d[A-Za-z]\b)[A-Za-zα-ωΑ-Ω])"), " × "),
]

# 数字下标映射（化学式/离子用）
_DIGIT_SUB = {d: _SUB_MAP[d] for d in "0123456789"}
_DIGIT_SUP = {d: _SUP_MAP[d] for d in "0123456789"}


def _chem_formula(m: re.Match) -> str:
    """分子内每个元素后的数字 -> Unicode 下标；整体不含数字则原样返回（如 NaCl/ABC）。"""
    token = m.group(0)
    if not any(c.isdigit() for c in token):
        return token
    return re.sub(r"([A-Za-z])(\d+)", lambda mm: mm.group(1) + "".join(
        _DIGIT_SUB.get(d, d) for d in mm.group(2)), token)


def _sup_single(m: re.Match) -> str:
    c = m.group(1)
    return _SUP_MAP.get(c, f"^{c}")


def _sub_inner(inner: str) -> str:
    """下标内容整体转 Unicode；任一字符无映射则原样保留 _{…}（触发 warnings）。"""
    if inner and all(c in _SUB_MAP for c in inner):
        return "".join(_SUB_MAP[c] for c in inner)
    return "_{" + inner + "}"


def _ion_simple(m: re.Match) -> str:
    """Na+ / Cu2+ 类：元素(+电荷位数)+电荷符号 -> Unicode 上标。"""
    elem, charge_digits, sign = m.group(1), m.group(2), m.group(3)
    sup = "".join(_DIGIT_SUP[d] for d in charge_digits) + _SUP_MAP[sign]
    return f"{elem}{sup}"


def _ion_poly(m: re.Match) -> str:
    """SO4^2- / SO4 2- 类：原子团数字先下标，电荷上标。"""
    body, charge_digits, sign = m.group(1), m.group(2), m.group(3)
    # body 里的数字转下标（如 SO4 -> SO₄）
    body_out = re.sub(r"(?<=[A-Za-z])(\d+)", lambda mm: "".join(
        _DIGIT_SUB[d] for d in mm.group(1)), body)
    sup = "".join(_DIGIT_SUP[d] for d in charge_digits) + _SUP_MAP[sign]
    return f"{body_out}{sup}"


def transcribe_by_rules(text: str) -> tuple[str, list[str], list[str]]:
    """规则转译主入口。

    返回 (转译文本, 命中的规则名列表, 遗留未转换记号列表)。
    遗留记号非空说明规则覆盖不了，调用方应走 LLM 或提示用户。
    """
    applied: list[str] = []
    out = text

    for name, pattern, repl in _LATEX_RULES:
        new_out, n = pattern.subn(repl, out)
        if n:
            applied.append(name)
            out = new_out

    # 化学式规则要在离子规则前跑会互相干扰：先离子（带电荷标记），再化学式
    for name, pattern, repl in _PLAIN_RULES:
        new_out, n = pattern.subn(repl, out)
        if n:
            applied.append(name)
            out = new_out

    residue = detect_residue(out)
    return out, applied, residue


def _speak_atom(text: str) -> str:
    """把紧凑数学片段转成更适合读屏连续朗读的结构文本。"""
    out = text.strip()
    out = out.replace("-∞", "负无穷")
    out = out.replace("∞", "无穷")
    for sym, spoken in _GREEK_SPOKEN.items():
        out = out.replace(sym, spoken)
    out = re.sub(r"(?<![\w])-(?=[A-Za-z0-9\u4e00-\u9fff])", "负 ", out)

    def exp_repl(m: re.Match) -> str:
        base = m.group(1)
        exp = _speak_atom(m.group(2))
        return f"{base} 的 {exp} 次方"

    out = re.sub(r"([A-Za-z])\^\(([^()]*)\)", exp_repl, out)
    out = out.replace("×", " 乘以 ")
    out = out.replace("+", " 加 ")
    out = out.replace("=", " 等于 ")
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _structured_integral(m: re.Match) -> str:
    lo, hi, body, var = m.group(1), m.group(2), m.group(3), m.group(4)
    body = body.rstrip(" ×")
    return f"从 {_speak_atom(lo)} 到 {_speak_atom(hi)}，对 {_speak_atom(body)}，关于 {var} 积分"


def _structured_bare_integral(m: re.Match) -> str:
    body, var = m.group(1), m.group(2)
    body = body.rstrip(" ×")
    return f"对 {_speak_atom(body)}，关于 {var} 积分"


def to_spoken_structured(text: str) -> tuple[str, list[str]]:
    """把 compact 结果进一步转成结构朗读稿，不解释公式用途，只显式化视觉结构。"""
    out = text
    applied: list[str] = []

    pattern_bounded = re.compile(r"积分\(从([^)]+?)到([^)]+?)\)\s*([^。；;\n，,]*?)\s*d\s*([A-Za-z])")
    out, n = pattern_bounded.subn(_structured_integral, out)
    if n:
        applied.append("结构朗读-定积分")

    pattern_bare = re.compile(r"积分\s*([^。；;\n，,]*?)\s*d\s*([A-Za-z])")
    out, n = pattern_bare.subn(_structured_bare_integral, out)
    if n:
        applied.append("结构朗读-积分")

    # 未被积分规则消费的指数，也要把作用范围说出来。
    out, n = re.subn(r"([A-Za-z])\^\(([^()]*)\)", lambda m: f"{m.group(1)} 的 {_speak_atom(m.group(2))} 次方", out)
    if n:
        applied.append("结构朗读-指数")

    out = _speak_atom(out)
    return out, applied


# ---------- 遗留记号检测（决定是否需要 LLM） ----------

_RESIDUE_PATTERNS = [
    ("LaTeX命令", re.compile(r"\\[a-zA-Z]+")),
    ("^记号上标", re.compile(r"(?<=\w)\^(?!\()")),  # ^(…) 复杂指数是协议允许的合法输出
    ("_记号下标", re.compile(r"(?<=\w)_")),
    ("sqrt记号", re.compile(r"\bsqrt\b")),
    ("ASCII比较符", re.compile(r"<=|>=|!=")),
    ("疑似化学式数字", re.compile(r"[A-Z][a-z]?\d+(?=[A-Z]|$|\s)")),
    ("视觉大运算符", re.compile(r"[∫∬∭∮∑∏]")),
    ("Unicode负号", re.compile(r"−")),
]


def detect_residue(text: str) -> list[str]:
    """检测规则转译后仍存在的读屏不友好记号，返回命中的类别名。"""
    found = []
    for name, pattern in _RESIDUE_PATTERNS:
        if pattern.search(text):
            found.append(name)
    return found


# ---------- 读屏友好空格（协议第 4 条通用排版） ----------

_CJK = r"\u4e00-\u9fff"


def add_cjk_spacing(text: str) -> str:
    """中文与 ASCII 字母/数字之间补一个空格，优化读屏断句。只补不删。
    例外：「3次√」这类整体记号不打散——先用占位符保护「次√」。"""
    out = text.replace("次√", "\x00CI_GEN\x00")
    out = re.sub(f"([{_CJK}])([A-Za-z0-9√∫≤≥≠±∞∈∥⊥∠△])", r"\1 \2", out)
    out = re.sub(f"([A-Za-z0-9%℃°])([{_CJK}])", r"\1 \2", out)
    out = re.sub(r"(\d) (\x00CI_GEN\x00)", r"\1\2", out)  # 数字与次√之间不补空格
    out = out.replace("\x00CI_GEN\x00", "次√")
    return out


def rule_transcribe(text: str, with_spacing: bool = True, profile: str = "unicode_compact") -> dict:
    """对外规则入口：返回与接口一致的子集结构。"""
    out, applied, residue = transcribe_by_rules(text)
    if profile == "spoken_structured":
        out, extra = to_spoken_structured(out)
        applied.extend(extra)
        residue = detect_residue(out)
    if with_spacing:
        out = add_cjk_spacing(out)
    return {
        "transcribed_text": out,
        "applied": applied,
        "residue": residue,
        "confidence": "high" if applied and not residue else ("medium" if not residue else "low"),
    }
