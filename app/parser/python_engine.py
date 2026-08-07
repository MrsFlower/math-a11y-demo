"""A 路线：纯 Python 解析引擎。

流程：LaTeX --latex2mathml--> MathML --XML 遍历--> 结构树 + 中文朗读文本。
不依赖 Node.js，不依赖任何模型，保证离线可用。
"""
from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET

import latex2mathml.converter

# ---------------- 符号中文映射 ----------------

GREEK = {
    "α": "阿尔法", "β": "贝塔", "γ": "伽马", "δ": "德尔塔", "ε": "艾普西龙",
    "ζ": "泽塔", "η": "伊塔", "θ": "西塔", "ι": "约塔", "κ": "卡帕",
    "λ": "拉姆达", "μ": "缪", "ν": "纽", "ξ": "克西", "ο": "奥密克戎",
    "π": "派", "ρ": "柔", "σ": "西格玛", "τ": "陶", "υ": "宇普西龙",
    "φ": "斐", "χ": "希", "ψ": "普西", "ω": "欧米伽",
    "Γ": "大写伽马", "Δ": "大写德尔塔", "Θ": "大写西塔", "Λ": "大写拉姆达",
    "Ξ": "大写克西", "Π": "大写派", "Σ": "大写西格玛", "Φ": "大写斐",
    "Ψ": "大写普西", "Ω": "大写欧米伽",
}

OPERATORS = {
    "+": "加", "-": "减", "−": "减", "±": "正负", "∓": "负正",
    "=": "等于", "≠": "不等于", "≈": "约等于", "≡": "恒等于",
    "<": "小于", ">": "大于", "≤": "小于等于", "≥": "大于等于",
    "×": "乘", "⋅": "点乘", "·": "点乘", "∗": "乘", "/": "除以", "÷": "除以",
    "∫": "积分", "∬": "二重积分", "∭": "三重积分", "∮": "环路积分",
    "∑": "求和", "∏": "连乘", "√": "根号",
    "∞": "无穷大", "∂": "偏导", "∇": "梯度", "→": "趋向于", "↦": "映射到",
    "∈": "属于", "∉": "不属于", "⊂": "包含于", "∪": "并", "∩": "交",
    "∀": "对任意", "∃": "存在", "!": "的阶乘", "%": "百分号",
    "(": "左括号", ")": "右括号", "[": "左中括号", "]": "右中括号",
    "{": "左大括号", "}": "右大括号", "|": "竖线", ",": "逗号", ";": "分号",
    "′": "一撇", "″": "两撇", "…": "省略号", "⋯": "省略号",
}

# mover 上方记号的语义化读法：{记号: (label, spoken模板)}
ACCENTS = {
    "˙": ("点记号（对时间求导）", "{b} 点"),
    ".": ("点记号（对时间求导）", "{b} 点"),
    "¨": ("双点记号（二阶时间导数）", "{b} 双点"),
    "¯": ("上横线", "{b} 上横线"),
    "‾": ("上横线", "{b} 上横线"),
    "―": ("上横线", "{b} 上横线"),
    "^": ("尖帽记号", "{b} 帽"),
    "ˆ": ("尖帽记号", "{b} 帽"),
    "~": ("波浪记号", "{b} 波浪"),
    "˜": ("波浪记号", "{b} 波浪"),
    "→": ("向量箭头", "向量 {b}"),
    "⃗": ("向量箭头", "向量 {b}"),
}

# 数学字母数字符号（U+1D400–U+1D7FF）中的粗体区段：粗体在物理/工程习惯里表向量
BOLD_RANGES = (
    (0x1D400, 0x1D433),  # bold 拉丁
    (0x1D468, 0x1D49B),  # bold italic 拉丁
    (0x1D4D0, 0x1D503),  # bold script
    (0x1D56C, 0x1D59F),  # bold fraktur
    (0x1D5D4, 0x1D607),  # sans bold
    (0x1D63C, 0x1D66F),  # sans bold italic
    (0x1D6A8, 0x1D6E1),  # bold 希腊
    (0x1D71C, 0x1D755),  # bold italic 希腊
)


def _normalize_ident(t: str) -> tuple[str, bool]:
    """把数学字母变体（粗体/斜体 𝐮 等）归一化回普通字符，并识别是否粗体。"""
    bold = any(a <= ord(ch) <= b for ch in t for a, b in BOLD_RANGES)
    clean = unicodedata.normalize("NFKC", t)
    return clean, bold

# 不需要朗读的隐式符号（函数应用、隐式乘法、不可见逗号等）
INVISIBLE = {"\u2061", "\u2062", "\u2063", "\u2064", "\u00a0", ""}

BIG_OPS = {"∫": "积分", "∬": "二重积分", "∮": "环路积分", "∑": "求和", "∏": "连乘"}


def _spoken_token(text: str) -> str:
    """单个符号的中文读法。"""
    text = text.strip()
    if text in INVISIBLE:
        return ""
    if text in GREEK:
        return GREEK[text]
    if text in OPERATORS:
        return OPERATORS[text]
    return text


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


class _Ctx:
    """遍历上下文：负责节点编号。"""

    def __init__(self):
        self.counter = 0

    def next_id(self) -> str:
        nid = f"n{self.counter}"
        self.counter += 1
        return nid


def _node(ctx: _Ctx, role: str, label: str, text: str, spoken: str, children=None):
    return {
        "id": ctx.next_id(),
        "role": role,
        "label": label,
        "text": text,
        "spoken": spoken,
        "children": children or [],
    }


def _elem_text(el) -> str:
    return (el.text or "").strip()


def _walk(el, ctx: _Ctx):
    """递归遍历 MathML 元素，返回结构树节点（可能为 None 表示忽略）。"""
    tag = _strip_ns(el.tag)

    if tag in ("math", "mstyle", "semantics", "mpadded", "mphantom"):
        children = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(children) == 1:
            return children[0]
        return _row(ctx, children)

    if tag == "mrow":
        children = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(children) == 1:
            return children[0]
        # 识别「括号包矩阵」：( mtable ) -> 矩阵整体
        if (
            len(children) == 3
            and children[0]["role"] == "operator"
            and children[0]["text"] in "([{"
            and children[1]["role"] == "matrix"
            and children[2]["role"] == "operator"
        ):
            m = children[1]
            m["text"] = children[0]["text"] + m["text"] + children[2]["text"]
            return m
        return _row(ctx, children)

    if tag == "mi":
        t = _elem_text(el)
        if t in INVISIBLE:
            return None
        # 归一化数学字母变体（𝐮 等）；粗体按物理习惯读作向量
        t, bold = _normalize_ident(t)
        if t in INVISIBLE:
            return None
        # latex2mathml 会把 \pm、\infty 等符号放进 mi，按运算符处理
        if t in OPERATORS:
            return _node(ctx, "operator", f"运算符 {t}（{OPERATORS[t]}）", t, OPERATORS[t])
        spoken = GREEK.get(t, t)
        label = f"标识符 {t}" if t not in GREEK else f"希腊字母 {t}（{spoken}）"
        if bold:
            spoken = f"向量 {spoken}"
            label = f"粗体标识符 {t}（按惯例读作向量）"
        return _node(ctx, "identifier", label, t, spoken)

    if tag == "mn":
        t = _elem_text(el)
        return _node(ctx, "number", f"数字 {t}", t, t)

    if tag == "mo":
        t = _elem_text(el)
        if t in INVISIBLE:
            return None
        spoken = _spoken_token(t)
        return _node(ctx, "operator", f"运算符 {t}（{spoken}）", t, spoken)

    if tag == "mtext":
        t = _elem_text(el)
        if not t:
            return None
        return _node(ctx, "text", f"文字 {t}", t, t)

    if tag in ("mspace", "maligngroup", "malignmark", "none"):
        return None

    if tag == "mfrac":
        parts = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(parts) != 2:
            return _row(ctx, parts)
        num, den = parts
        # 导数特例：∂T/∂t 读作「T 对 t 的偏导数」而不是普通分数
        deriv = _derivative_spoken(num, den)
        if deriv:
            label, spoken = deriv
            text = f"({num['text']})/({den['text']})"
            return _node(ctx, "derivative", label, text, spoken, [num, den])
        text = f"({num['text']})/({den['text']})"
        spoken = f"分数，分子是 {num['spoken']}，分母是 {den['spoken']}，分数结束"
        return _node(ctx, "fraction", "分数", text, spoken, [num, den])

    if tag == "msqrt":
        inner = [c for c in (_walk(ch, ctx) for ch in el) if c]
        body = inner[0] if len(inner) == 1 else _row(ctx, inner)
        text = f"√({body['text']})"
        spoken = f"根号下 {body['spoken']}，根号结束"
        return _node(ctx, "sqrt", "平方根", text, spoken, [body])

    if tag == "mroot":
        parts = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(parts) != 2:
            return _row(ctx, parts)
        body, index = parts
        text = f"{index['text']}√({body['text']})"
        spoken = f"{index['spoken']} 次根号下 {body['spoken']}，根号结束"
        return _node(ctx, "root", f"{index['text']} 次方根", text, spoken, [body, index])

    if tag == "msup":
        parts = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(parts) != 2:
            return _row(ctx, parts)
        base, exp = parts
        text = f"{base['text']}^({exp['text']})"
        if exp["text"] == "2":
            spoken = f"{base['spoken']} 的平方"
        elif exp["text"] == "3":
            spoken = f"{base['spoken']} 的立方"
        else:
            spoken = f"{base['spoken']} 的 {exp['spoken']} 次方"
        return _node(ctx, "superscript", "上标（乘方）", text, spoken, [base, exp])

    if tag == "msub":
        parts = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(parts) != 2:
            return _row(ctx, parts)
        base, sub = parts
        text = f"{base['text']}_({sub['text']})"
        spoken = f"{base['spoken']} 下标 {sub['spoken']}"
        return _node(ctx, "subscript", "下标", text, spoken, [base, sub])

    if tag in ("msubsup", "munderover"):
        parts = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(parts) != 3:
            return _row(ctx, parts)
        base, lo, hi = parts
        if base["text"] in BIG_OPS:
            opname = BIG_OPS[base["text"]]
            text = f"{base['text']}_({lo['text']})^({hi['text']})"
            spoken = f"{opname}，下限 {lo['spoken']}，上限 {hi['spoken']}"
            return _node(
                ctx, "bigop", f"{opname}（含上下限）", text, spoken, [base, lo, hi]
            )
        text = f"{base['text']}_({lo['text']})^({hi['text']})"
        spoken = f"{base['spoken']} 下标 {lo['spoken']}，上标 {hi['spoken']}"
        return _node(ctx, "subsup", "上下标", text, spoken, [base, lo, hi])

    if tag in ("munder", "mover"):
        parts = [c for c in (_walk(ch, ctx) for ch in el) if c]
        if len(parts) != 2:
            return _row(ctx, parts)
        base, script = parts
        # 上方记号语义化：\dot q 读「q 点」、\vec v 读「向量 v」等
        if tag == "mover" and script["text"] in ACCENTS:
            acc_label, acc_tpl = ACCENTS[script["text"]]
            text = f"{base['text']}[{script['text']}]"
            spoken = acc_tpl.format(b=base["spoken"])
            return _node(ctx, "accent", acc_label, text, spoken, [base, script])
        pos = "下方" if tag == "munder" else "上方"
        text = f"{base['text']}[{script['text']}]"
        spoken = f"{base['spoken']}，{pos}标注 {script['spoken']}"
        return _node(ctx, "underover", f"{pos}标注", text, spoken, [base, script])

    if tag == "mtable":
        rows = []
        for tr in el:
            if _strip_ns(tr.tag) != "mtr":
                continue
            cells = []
            for td in tr:
                if _strip_ns(td.tag) != "mtd":
                    continue
                inner = [c for c in (_walk(ch, ctx) for ch in td) if c]
                cell = inner[0] if len(inner) == 1 else _row(ctx, inner)
                cells.append(cell)
            row_text = ", ".join(c["text"] for c in cells)
            row_spoken = "，".join(c["spoken"] for c in cells)
            rows.append(
                _node(ctx, "matrix-row", f"第 {len(rows) + 1} 行", row_text, row_spoken, cells)
            )
        n_rows = len(rows)
        n_cols = max((len(r["children"]) for r in rows), default=0)
        text = "[" + "; ".join(r["text"] for r in rows) + "]"
        spoken_rows = "；".join(
            f"第 {i + 1} 行：{r['spoken']}" for i, r in enumerate(rows)
        )
        spoken = f"{n_rows} 行 {n_cols} 列的矩阵，{spoken_rows}，矩阵结束"
        return _node(ctx, "matrix", f"矩阵 {n_rows}×{n_cols}", text, spoken, rows)

    if tag == "mfenced":  # 部分转换器会输出 mfenced
        inner = [c for c in (_walk(ch, ctx) for ch in el) if c]
        body = inner[0] if len(inner) == 1 else _row(ctx, inner)
        text = f"({body['text']})"
        spoken = f"括号里是 {body['spoken']}，括号结束"
        return _node(ctx, "fenced", "括号", text, spoken, [body])

    # 未识别标签：继续遍历子元素
    children = [c for c in (_walk(ch, ctx) for ch in el) if c]
    if not children:
        t = _elem_text(el)
        if not t:
            return None
        return _node(ctx, "token", f"符号 {t}", t, _spoken_token(t))
    if len(children) == 1:
        return children[0]
    return _row(ctx, children)


def _row(ctx: _Ctx, children):
    children = _merge_nabla(ctx, children)
    text = " ".join(c["text"] for c in children if c["text"])
    spoken = " ".join(c["spoken"] for c in children if c["spoken"])
    return _node(ctx, "row", "组合表达式", text, spoken, children)


def _merge_nabla(ctx: _Ctx, children):
    """把「∇ ⋅」合并读作散度、「∇ ×」合并读作旋度（物理公式常见组合）。"""
    out = []
    i = 0
    while i < len(children):
        c = children[i]
        if (
            c.get("text") == "∇"
            and i + 1 < len(children)
            and children[i + 1].get("text") in ("⋅", "·", "×")
        ):
            op = children[i + 1]["text"]
            name = "散度" if op in ("⋅", "·") else "旋度"
            out.append(
                _node(ctx, "operator", f"{name}算子 ∇{op}", f"∇{op}", name)
            )
            i += 2
            continue
        out.append(c)
        i += 1
    return out


# 导数分子/分母模式：∂、∂^(2)、d 开头（_row 的 text 用空格拼接）
_PARTIAL_RE = re.compile(r"^∂(?:\^\((\d+)\))?\s*(.*)$", re.S)
_TOTAL_RE = re.compile(r"^d(?:\^\((\d+)\))?\s+(.*)$", re.S)


def _strip_deriv_prefix(spoken: str, symbol_spoken: str) -> str:
    """从朗读文本里去掉开头的「偏导/d」及其乘方后缀，留下变量本身。"""
    s = re.sub(
        rf"^{re.escape(symbol_spoken)}(?: 的平方| 的立方| 的 \S+ 次方)?\s*", "", spoken
    ).strip()
    return re.sub(r"( 的平方| 的立方| 的 \S+ 次方)$", "", s).strip()


def _derivative_spoken(num: dict, den: dict):
    """识别导数形式的分数，返回 (label, spoken)；不是导数返回 None。

    支持：∂T/∂t（偏导）、∂²T/∂x²（高阶偏导）、dT/dt（常导）、
    纯算子 ∂/∂x（读「对 x 求偏导」，后接括号内容）。
    """
    for pat, symbol, symbol_spoken, kind in (
        (_PARTIAL_RE, "∂", "偏导", "偏导数"),
        (_TOTAL_RE, "d", "d", "导数"),
    ):
        m_num = pat.match(num["text"])
        m_den = pat.match(den["text"])
        if not (m_num and m_den):
            continue
        var = _strip_deriv_prefix(den["spoken"], symbol_spoken)
        if not var:
            continue  # 分母没有变量，不是导数
        order = m_num.group(1) or ("2" if "^" in den["text"] else None)
        func = _strip_deriv_prefix(num["spoken"], symbol_spoken)
        order_txt = f" {order} 阶" if order and order != "1" else ""
        if not func:
            # 纯算子形式 ∂/∂x，后面通常跟括号内容
            verb = "求偏导" if kind == "偏导数" else "求导"
            return (f"{kind}算子", f"对 {var}{order_txt} {verb}".replace("  ", " "))
        return (kind, f"{func} 对 {var} 的{order_txt}{kind}")
    return None


def _tidy_spoken(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def parse_latex(latex: str) -> dict:
    """主入口：LaTeX -> {mathml, tree, speech_text}，失败抛出 ValueError。"""
    latex = latex.strip()
    if not latex:
        raise ValueError("公式为空，请输入 LaTeX。")
    try:
        mathml = latex2mathml.converter.convert(latex)
    except Exception as exc:  # latex2mathml 的异常类型不统一，这里统一兜住
        raise ValueError(f"LaTeX 解析失败：{exc}") from exc

    # 安全加固：MathML 由 latex2mathml 生成，正常不含 DTD/实体；若出现则直接拒绝，
    # 避免实体扩展类攻击（billion laughs / XXE）。
    lowered = mathml.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("MathML 中含非法 DTD/实体声明，已拒绝解析。")
    try:
        root_el = ET.fromstring(mathml)
    except ET.ParseError as exc:
        raise ValueError(f"MathML 解析失败：{exc}") from exc

    ctx = _Ctx()
    tree = _walk(root_el, ctx)
    if tree is None:
        raise ValueError("公式内容为空或无法识别。")
    tree["label"] = "公式整体"
    speech = _tidy_spoken(tree["spoken"])
    return {"mathml": mathml, "tree": tree, "speech_text": speech}


def tree_outline(tree: dict, depth: int = 0, max_depth: int = 6) -> str:
    """把结构树转成缩进文本，供大模型和「纯文本版」使用。"""
    lines = [f"{'  ' * depth}- [{tree['id']}] {tree['label']}：{tree['text']}"]
    if depth < max_depth:
        for ch in tree.get("children", []):
            lines.append(tree_outline(ch, depth + 1, max_depth))
    return "\n".join(lines)


def find_node(tree: dict, node_id: str):
    """按 id 在结构树里找节点。"""
    if tree.get("id") == node_id:
        return tree
    for ch in tree.get("children", []):
        found = find_node(ch, node_id)
        if found:
            return found
    return None
