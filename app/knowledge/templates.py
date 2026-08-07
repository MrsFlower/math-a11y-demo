# -*- coding: utf-8 -*-
"""轻量公式模板系统：为大模型解释提供领域知识锚点（grounding）。

设计原则（对齐第二层任务说明）：
- 不做复杂 RAG，只用正则/结构特征识别常见公式类别。
- 模板不产出「最终回答」，只提供「核心理解 + 变量角色 + 必须覆盖的要点」，
  交给 LLM 结合具体公式生成解释；无模板时走通用解释并标低置信度。
- 识别有先后：越具体的越先匹配（求根、傅里叶）在前，通用的（大运算符）在后。
"""
from __future__ import annotations

import re

__all__ = ["detect_template", "TEMPLATES"]


def _norm(latex: str) -> str:
    """归一化 LaTeX 便于特征匹配：去空白、去 \\left \\right \\, \\! 等排版记号。"""
    s = latex
    for token in (r"\left", r"\right", r"\,", r"\!", r"\;", r"\:", r"\ ", "{", "}", " "):
        s = s.replace(token, "")
    return s


# 每个模板：id / formula_name / domain / purpose / intuition_hint /
# key_understanding（给 LLM 的核心理解）/ variables（变量角色）/ must_mention（反流水账必须命中词）/
# strength（strong=特征明确几乎不会误判，允许 confidence=high；generic=兄弟类别多、只能到 medium）
TEMPLATES = [
    {
        "id": "quadratic_formula",
        "formula_name": "一元二次方程求根公式",
        "domain": "代数",
        "purpose": "由二次方程的三个系数直接算出未知数的两个可能取值。",
        "intuition_hint": "它把配方、开方的过程一次性打包成公式，用来直接得到解；正负号给出两个候选解，"
        "根号里的判别式决定这两个解到底长什么样。",
        "key_understanding": "把二次方程的两个根直接表示出来，用来一次性求出未知数的两个可能取值；"
        "正负号对应两个解；根号里的 b 的平方减 4ac 是判别式，它决定实数解的个数（大于零两个、等于零一个、小于零没有实数解）。",
        "variables": [
            {"symbol": "x", "role": "未知数", "meaning": "要求解的量，即方程的根。"},
            {"symbol": "a", "role": "二次项系数", "meaning": "控制二次项，不能为零，否则不是二次方程。"},
            {"symbol": "b", "role": "一次项系数", "meaning": "影响对称轴位置。"},
            {"symbol": "c", "role": "常数项", "meaning": "与判别式共同决定解的情况。"},
        ],
        "must_mention": ["判别式", "两个解"],
        "strength": "strong",
    },
    {
        "id": "fourier_transform",
        "formula_name": "傅里叶变换",
        "domain": "微积分 / 信号分析",
        "purpose": "把一个按时间或位置描述的函数，转换成按频率描述。",
        "intuition_hint": "拿原函数去和某个指定频率的复指数波做匹配，匹配得越强就表示"
        "原函数里这个频率的成分越多；对所有频率都做一遍，就得到频谱，用来看清信号由哪些频率组成。",
        "key_understanding": "把函数拆成不同频率成分；从负无穷到正无穷的积分表示在整个定义范围上"
        "累积「这个频率有多少」；指数项是一个可调频率的探针。",
        "variables": [
            {"symbol": "f", "role": "原始函数", "meaning": "待分析的信号，按时间或位置描述。"},
            {"symbol": "\u03c9", "role": "频率变量", "meaning": "正在检查的频率（欧米伽）。"},
            {"symbol": "x", "role": "积分变量", "meaning": "原函数的自变量（时间或位置），会被积掉。"},
        ],
        "must_mention": ["频率"],
        "strength": "strong",
    },
    {
        "id": "derivative",
        "formula_name": "导数 / 偏导数",
        "domain": "微积分",
        "purpose": "描述一个量相对于另一个量的变化率。",
        "intuition_hint": "它回答「自变量变化一点点时，因变量变化多快」；偏导是在其他变量"
        "暂时固定的前提下，只看某一个方向上的变化。",
        "key_understanding": "导数是变化率、是局部斜率；偏导数是在固定其他变量时对某一个变量的变化率，"
        "常用于描述随时间或空间的演化。",
        "variables": [],
        "must_mention": ["变化率"],
        "strength": "strong",
    },
    {
        "id": "matrix_system",
        "formula_name": "矩阵 / 线性方程组",
        "domain": "线性代数",
        "purpose": "用按行列组织的结构，紧凑地表达一组线性关系或线性变换。",
        "intuition_hint": "矩阵不是一堆散数字，而是有行列结构的关系表；在线性方程组里，"
        "每一行通常对应一条约束（一个方程）。",
        "key_understanding": "矩阵按行列组织关系；线性方程组里每一行是一条约束；"
        "矩阵乘向量可以理解为对向量做线性变换或代入一组方程。",
        "variables": [],
        "must_mention": ["约束", "线性"],
        "strength": "strong",
    },
    {
        "id": "big_operator",
        "formula_name": "求和 / 积分 / 连乘（带上下限的大运算符）",
        "domain": "微积分",
        "purpose": "把很多局部贡献按范围累积成一个整体量。",
        "intuition_hint": "上下限规定了累积的范围，主体规定了每一步在累积什么；"
        "求和是离散地加起来，积分是连续地累积。",
        "key_understanding": "上限下限定义范围，主体定义每一步累积什么；它们表达的是"
        "「把很多局部贡献合起来」的思想。",
        "variables": [],
        "must_mention": ["范围", "累积"],
        "strength": "generic",
    },
    {
        "id": "bayes",
        "formula_name": "贝叶斯公式 / 条件概率",
        "domain": "概率统计",
        "purpose": "在拿到新证据之后，更新对某个事件发生可能性的判断。",
        "intuition_hint": "它用来把「已知结果反推原因」变成可计算的事：先有一个先验判断，"
        "观察到新证据后，按证据支持程度把判断修正成后验概率。",
        "key_understanding": "竖线读作「在……条件下」；分子是「原因成立且能解释证据」的部分，"
        "分母是证据本身出现的总可能性；整个公式表示用新证据把先验概率更新为后验概率。",
        "variables": [
            {"symbol": "P(A|B)", "role": "后验概率", "meaning": "看到证据 B 之后，A 发生的概率。"},
            {"symbol": "P(B|A)", "role": "似然", "meaning": "假设 A 成立时，观察到证据 B 的概率。"},
            {"symbol": "P(A)", "role": "先验概率", "meaning": "没有任何证据时对 A 的初始判断。"},
            {"symbol": "P(B)", "role": "证据概率", "meaning": "证据 B 本身出现的总可能性，起归一化作用。"},
        ],
        "must_mention": ["更新", "证据"],
        "strength": "strong",
    },
    {
        "id": "expectation_variance",
        "formula_name": "期望 / 方差",
        "domain": "概率统计",
        "purpose": "用一个数概括随机量的整体表现：期望看平均水平，方差看波动大小。",
        "intuition_hint": "期望表示大量重复之后的长期平均结果；方差表示实际结果围绕平均值"
        "摆动得有多厉害，方差越大越不稳定。",
        "key_understanding": "期望是把每个可能取值按它出现的概率加权平均，用来表示长期平均水平；"
        "方差是「离均值偏差的平方」的期望，用来衡量波动程度；平方是为了不让正负偏差互相抵消。",
        "variables": [
            {"symbol": "X", "role": "随机变量", "meaning": "取值不确定的量，比如一次投掷的点数。"},
        ],
        "must_mention": ["平均", "波动"],
        "strength": "strong",
    },
    {
        "id": "limit",
        "formula_name": "极限",
        "domain": "微积分",
        "purpose": "描述变量靠近某个值时，表达式趋近的结果。",
        "intuition_hint": "它不关心「恰好等于那一点时」的取值，而是关心「无限靠近时」的趋势；"
        "很多在那一点没有定义的表达式，趋近过程却有确定的结果。",
        "key_understanding": "极限表示变量无限靠近某个值（或无穷）时表达式的趋近结果；"
        "它是导数、积分等概念的地基，因为它们都定义为某种趋近过程的结果。",
        "variables": [],
        "must_mention": ["趋近"],
        "strength": "strong",
    },
]

_BY_ID = {t["id"]: t for t in TEMPLATES}


def detect_template(latex: str, tree: dict | None = None) -> dict | None:
    """根据 LaTeX（辅以结构树）识别候选模板，返回模板 dict 或 None。"""
    s = _norm(latex)

    # 1) 求根公式：含 \pm、\sqrt，且判别式特征 b^2-4ac / 分母 2a
    if r"\pm" in s and r"\sqrt" in s and (re.search(r"4ac|4\*ac|b\^2-4ac", s) or "2a" in s):
        return _BY_ID["quadratic_formula"]

    # 2) 傅里叶变换：无穷积分 + 复指数探针
    has_inf_int = r"\int" in s and r"\infty" in s
    has_complex_exp = re.search(r"e\^.*(-?i\\?omega|-?i\w)", s) or r"i\omega" in s
    if has_inf_int and (has_complex_exp or re.search(r"f\(", s)):
        if has_complex_exp:
            return _BY_ID["fourier_transform"]

    # 3) 贝叶斯 / 条件概率：含 P(·|·) 条件记号（\mid 已被 _norm 保留，| 直接匹配）
    if re.search(r"P\(.+(\||\\mid).+\)", s):
        return _BY_ID["bayes"]

    # 4) 期望 / 方差：E[X]、\mathbb{E}、Var(·)、D(X)、\sigma^2 记号
    if re.search(r"(\\mathbb\{?E|E\[|\\operatorname\{?(Var|E)|Var\(|\\mathrm\{?Var)", latex.replace(" ", "")):
        return _BY_ID["expectation_variance"]

    # 5) 极限：\lim（含下标趋近目标）
    if r"\lim" in latex:
        return _BY_ID["limit"]

    # 6) 导数 / 偏导数：\frac{d..}{d..} 或含 \partial
    if r"\partial" in s or re.search(r"\\frac\\?d[a-zA-Z].*\\?d[a-zA-Z]", s) or re.search(r"\\frac{d", latex):
        return _BY_ID["derivative"]

    # 7) 矩阵 / 线性方程组
    if re.search(r"\\begin\{[pbvV]?matrix\}", latex) or "matrix" in latex:
        return _BY_ID["matrix_system"]

    # 8) 求和 / 积分 / 连乘（带上下限的大运算符）——通用兜底类别
    if re.search(r"\\(sum|int|prod|oint|iint)", latex):
        return _BY_ID["big_operator"]

    return None


def grounding_text(tpl: dict) -> str:
    """把模板整理成给 LLM 的 grounding 段落。"""
    lines = [
        f"识别到候选公式类别：{tpl['formula_name']}（领域：{tpl['domain']}）。",
        f"该类公式的用途：{tpl['purpose']}",
        f"核心理解（务必融入解释）：{tpl['key_understanding']}",
        f"直觉提示：{tpl['intuition_hint']}",
    ]
    if tpl.get("variables"):
        vs = "；".join(f"{v['symbol']}={v['role']}（{v['meaning']}）" for v in tpl["variables"])
        lines.append(f"常见变量角色参考：{vs}")
    if tpl.get("must_mention"):
        lines.append(f"解释里应自然出现这些关键词之一或全部：{('、'.join(tpl['must_mention']))}。")
    lines.append("注意：以上为根据结构推断的候选类别，若与具体公式不符，请以实际公式为准并降低置信度。")
    return "\n".join(lines)
