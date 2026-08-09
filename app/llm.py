"""大模型调用层：OpenAI 兼容接口（默认阿里云百炼 Qwen）。

设计原则：
1. Key 只从环境变量读取，代码中不出现任何密钥。
2. 没有 Key 或调用失败时，自动降级为基于结构树的本地规则解释，
   保证「结构树 + 朗读文本 + 基础解释」离线也可用。
3. 输出稳定为 dict（JSON 可序列化），前端只负责展示。
"""
from __future__ import annotations

import json
import re

import httpx

from . import config
from .knowledge import templates
from .parser.python_engine import tree_outline

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# 当前使用的模型下标（百炼免费额度按模型 Code 独立，403 额度用尽后永久前进到下一个）
_model_idx = 0

# Qwen3 系混合思考模型默认开思考，生成 JSON 要 40~60s+ 易超时；
# 讲解任务不需深度推理，默认关闭思考。若接入点不认该参数（400）则自动去掉并记住。
_supports_enable_thinking = True


def current_model() -> str:
    return config.LLM_MODELS[min(_model_idx, len(config.LLM_MODELS) - 1)]


def _quota_exhausted(exc: httpx.HTTPStatusError) -> bool:
    """判断是否为额度用尽/限流类错误（如百炼 AllocationQuota.FreeTierOnly）。"""
    return exc.response.status_code in (403, 429)

EXPLAIN_SYSTEM = """你是一位面向视障学生的数学讲解老师。你的目标不是把公式按顺序念一遍，
而是让学生听完后“理解这个公式在干什么”。你的讲解会被屏幕阅读器逐字朗读。

硬性要求：
1. 只输出 JSON，不要 Markdown、代码块标记或任何其他文字。
2. 解释文字里禁止出现 LaTeX 源码、星号、井号等符号；数学内容一律用中文口语（如“b 的平方”“根号下”）。
3. 讲解文字必须是纯中文，严禁夹杂普通英文单词；形容词、动词、名词一律用中文表达。
   仅允许数学变量名（x、F、T 等单字母记号）和标准函数名（sin、log、Var 等）。英文概念一律翻译成中文。
4. 必须按“先用途、再直觉、再变量角色、再结构、再概念”的顺序组织。

反流水账约束（重要）：
- 禁止只复述“谁加谁、谁乘谁、谁对谁积分”。
- 每一条 concept_layers 必须回答“为什么”或“用来做什么”，不能只描述形状；
  内容里要自然用到“表示”“用来”“意味着”“原因”“作用”这类解释性词语。
- 对公式名称不确定时，必须写“根据结构推断”并把 confidence 设为 low 或 medium，不要装作确定。
- 不要直接给题目答案，除非用户明确要求；默认目标是帮助理解公式。

保守性要求（对上下文不足的公式）：
- 很短、只有普通变量和基础运算的公式（如 a 加 b 等于 c），无法判断它在哪个具体场景，
  此时 confidence 不得为 high，公式名应写成“基础加法关系（根据结构推断）”这类形式。
- 讲法用“根据结构看，它像是在表达……”，不要说得像一个确定命名的公式或定理。

歧义处理要求（重要，防止误导盲人学生）：
- 同一个符号在不同学科含义不同（如 E 可以是能量、期望或杨氏模量，σ 可以是标准差、应力或电导率）。
  没有上下文时不要武断选定一种含义：在 variables 的 meaning 里列出最常见的一两种可能，
  并说明“具体含义取决于上下文”，同时把这种歧义写进 common_misunderstandings。
- 若用户提供了公式所在页面的上下文，优先用上下文确定符号含义和公式领域，并在讲解中自然体现判断依据。

上下文场景结合要求（重要，禁止就公式讲公式）：
- 若上下文表明公式所处场景（如选择题的某个选项、例题条件、定义、证明步骤），
  purpose、intuition 与 accessible_summary 的开头必须先用一两句话点明公式在这个场景里的
  位置与角色（如“这是问哪个广义积分收敛的选择题里的 D 选项”），再讲公式本身。
- 上下文涉及题目任务时，围绕任务讲这个公式为什么值得注意（如结合收敛性讲衰减快慢），
  但不要替用户做题、不要直接报选项答案。

只输出下面结构的 JSON（字段全部保留，数组至少给出有价值的内容）：
{
  "formula_name": "可能的公式名称；不确定就写‘未知公式（根据结构推断）’",
  "domain": "数学领域，如代数/微积分/线性代数/概率/物理数学/未确定",
  "confidence": "high / medium / low",
  "purpose": "这个公式通常用来做什么（不能是‘计算这个公式’这类空话）",
  "intuition": "不用符号，用一段话说清楚它的核心思想，至少 40 个中文字",
  "read_order": ["建议的听读顺序步骤1", "步骤2", "步骤3"],
  "variables": [{"symbol": "x", "role": "角色，如未知数", "meaning": "含义"}],
  "structure_layers": [{"title": "结构层标题", "content": "客观描述这一层的结构"}],
  "concept_layers": [{"title": "理解层标题", "content": "概念、直觉、为什么这么做"}],
  "common_misunderstandings": ["容易误解的点"],
  "suggested_questions": ["可以继续追问的问题1", "问题2", "问题3"],
  "accessible_summary": "适合直接复制给读屏器连续朗读的一段总结，把用途、直觉、关键角色串成一段话"
}"""

ASK_SYSTEM = """你是一位面向视障学生的数学讲解老师，正在就一个公式回答学生的追问。
回答会被屏幕阅读器朗读，要求：
1. 直接输出纯文本回答，不要 Markdown，不要 LaTeX 源码，数学内容用中文口语表达。
2. 回答必须纯中文，禁止夹杂普通英文单词（数学变量名与标准函数名除外）。
3. 回答控制在 200 字以内，先给结论，再给必要解释。
4. 如果问题与这个公式无关，礼貌说明并引导回到公式本身。"""


NORMALIZE_SYSTEM = """你是一个公式格式转换器。用户给你一段从网页、PDF、聊天记录复制的公式文本，
或一段中文口语描述的公式，你把它转换成 LaTeX。

硬性要求：
1. 只输出一个 JSON 对象：{"latex": "...", "confidence": "high/medium/low", "notes": "一句话说明转换依据或提醒"}
2. 禁止输出任何解释性文字，禁止扩写或续写公式内容，只做格式转换。
3. 拿不准的部分按字面保守转换，并把 confidence 降为 low，在 notes 里提醒用户检查。
4. 如果文本里根本没有公式，输出 {"latex": "", "confidence": "low", "notes": "未识别出公式，请检查输入"}。"""


def _chat(messages: list[dict], temperature: float = 0.3) -> str:
    """调用 OpenAI 兼容 /chat/completions，返回文本内容，失败抛异常。

    沿 LLM_MODELS 备用链重试：某个模型免费额度用尽（403/429）时自动切换下一个。
    """
    global _model_idx, _supports_enable_thinking
    last_exc: Exception | None = None
    for idx in range(_model_idx, len(config.LLM_MODELS)):
        model = config.LLM_MODELS[idx]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if _supports_enable_thinking:
            payload["enable_thinking"] = False  # 关思考模式，否则 40~60s+ 易超时
        try:
            resp = httpx.post(
                f"{config.LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            _model_idx = idx  # 记住当前可用模型，后续请求直接用它
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            last_exc = exc
            if _quota_exhausted(exc):
                continue  # 额度用尽，试备用链下一个模型
            if (
                exc.response.status_code == 400
                and _supports_enable_thinking
                and "enable_thinking" in exc.response.text
            ):
                # 接入点不支持该参数：去掉后用同一个模型重试一次
                _supports_enable_thinking = False
                payload.pop("enable_thinking", None)
                resp = httpx.post(
                    f"{config.LLM_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {config.LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=_TIMEOUT,
                )
                resp.raise_for_status()
                _model_idx = idx
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            raise
    raise last_exc if last_exc else RuntimeError("未配置任何模型")


def _extract_json(text: str) -> dict:
    """从模型输出里稳妥地抠出 JSON 对象。"""
    text = text.strip()
    # 去掉可能的 ```json ... ``` 包裹
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


# ---------------- 规则兜底（无 Key / 调用失败时） ----------------

_ROLE_INTRO = {
    "fraction": "这是一个分数结构，先听分子，再听分母。",
    "sqrt": "这是一个根号结构，注意根号覆盖的范围。",
    "root": "这是一个高次方根结构。",
    "bigop": "这是一个带上下限的大运算符（如积分、求和），先确定范围，再看主体。",
    "matrix": "这是一个矩阵，按行逐个听每个元素。",
    "superscript": "这是一个乘方（上标）结构。",
    "subscript": "这是一个带下标的记号。",
    "row": "这是一个由多个部分组成的表达式，按从左到右的顺序理解。",
}


def _rules_layers(tree: dict, depth: int = 0, limit: int = 8) -> list[dict]:
    """按结构树逐层生成朴素解释。"""
    layers = []

    def visit(node: dict, d: int):
        if len(layers) >= limit:
            return
        role = node.get("role", "")
        if role in _ROLE_INTRO or d == 0:
            title = f"第 {d + 1} 层——{node['label']}"
            intro = _ROLE_INTRO.get(role, "")
            content = f"{intro} 这一部分读作：{node['spoken']}。".strip()
            layers.append({"title": title, "content": content})
        for ch in node.get("children", []):
            visit(ch, d + 1)

    visit(tree, depth)
    return layers


def _concept_layers_from_template(tpl: dict | None) -> list[dict]:
    """无 Key 时用模板知识构造概念层，保证至少 2 条且含“为什么/用来”语义。"""
    if not tpl:
        return [
            {"title": "它在表达什么", "content": "未能匹配到已知公式模板，以下为根据结构推断的理解："
             "请先听整体类型，再看主运算把哪些部分组合起来，这通常意味着一种变量之间的关系。"},
            {"title": "为什么要这样看", "content": "把公式拆成层次后，可以先把握整体作用，再逐层理解每个部分承担的角色，"
             "避免被符号淹没。"},
        ]
    return [
        {"title": "它的核心思想", "content": tpl["key_understanding"]},
        {"title": "直觉上在做什么", "content": tpl["intuition_hint"]},
    ]


def _rules_explanation(latex: str, tree: dict, speech_text: str) -> dict:
    """无 Key / 调用失败时的本地兜底，同样产出第二层 schema（基于模板知识）。"""
    tpl = templates.detect_template(latex, tree)
    if tpl:
        formula_name = tpl["formula_name"]
        domain = tpl["domain"]
        purpose = tpl["purpose"]
        intuition = tpl["intuition_hint"]
        variables = list(tpl.get("variables", []))
        confidence = "medium"
    else:
        formula_name = "未知公式（根据结构推断）"
        domain = "未确定"
        purpose = "根据结构推断，它把若干部分组合成一个整体表达式，具体用途需结合上下文判断。"
        intuition = "先把握最外层是什么运算，再看它把哪些部分联系在一起，往往就能看出它在描述一种关系。"
        variables = []
        confidence = "low"

    overview = f"{purpose} 当前为本地规则解释（未配置大模型 Key），结构导航与朗读不受影响。"
    concept_layers = _concept_layers_from_template(tpl)
    accessible = f"这可能是{formula_name}。{purpose}{intuition}整体读作：{speech_text}。"
    return {
        "formula_name": formula_name,
        "domain": domain,
        "confidence": confidence,
        "purpose": purpose,
        "intuition": intuition,
        "read_order": ["先听整体是什么类型", "再听主要运算把哪些部分联系起来", "最后逐层听局部细节"],
        "variables": variables,
        "structure_layers": _rules_layers(tree),
        "concept_layers": concept_layers,
        "common_misunderstandings": [],
        "suggested_questions": [
            "这个公式最外层是什么结构？",
            "公式里每个字母分别代表什么？",
            "这个公式一般在什么场景使用？",
        ],
        "accessible_summary": accessible,
        # ---- 向后兼容旧前端 ----
        "overview": overview,
        "layers": _rules_layers(tree),
        "source": "rules",
    }


# ---------------- 置信度校准（第三阶段：保守解释机制） ----------------

_CONF_ORDER = {"low": 0, "medium": 1, "high": 2}

# 判断“过于通用、上下文不足”的公式：去掉排版记号后很短，
# 且只包含普通变量、希腊字母和基础运算符（无积分/求和/矩阵等强结构特征）。
_TRIVIAL_ALLOWED = re.compile(
    r"^([a-zA-Z0-9+\-*/=^_(){}.,'\s]|\\(alpha|beta|gamma|delta|theta|lambda|mu|pi|sigma|omega|phi|cdot|times|div|pm)\b)*$"
)


def _is_trivial_latex(latex: str) -> bool:
    s = latex.strip()
    if len(s) > 40:
        return False
    return bool(_TRIVIAL_ALLOWED.match(s))


def _cap_confidence(result: dict, cap: str) -> None:
    cur = result.get("confidence", "medium")
    if _CONF_ORDER.get(cur, 1) > _CONF_ORDER[cap]:
        result["confidence"] = cap


def calibrate_confidence(latex: str, template: dict | None, explanation: dict) -> dict:
    """后处理：按模板命中情况和公式复杂度校准置信度，避免对上下文不足的公式过度自信。

    规则（对齐第三阶段任务说明）：
    - 强模板（strength=strong）命中：允许 high，不干预。
    - 通用模板（strength=generic）命中：最高 medium。
    - 未命中模板：短小简单公式最高 low，其余最高 medium；
      若公式名说得很确定（不含“推断/未知/可能”），追加“（根据结构推断）”后缀。
    """
    if template is not None:
        if template.get("strength", "generic") != "strong":
            _cap_confidence(explanation, "medium")
        return explanation

    trivial = _is_trivial_latex(latex)
    _cap_confidence(explanation, "low" if trivial else "medium")

    name = explanation.get("formula_name", "") or ""
    if name and not any(w in name for w in ("推断", "未知", "可能")):
        explanation["formula_name"] = f"{name}（根据结构推断）"
    return explanation


def _ensure_schema(result: dict, tree: dict, speech_text: str) -> dict:
    """补齐缺失字段 + 新旧 schema 双向映射，防止前端崩溃。"""
    result.setdefault("formula_name", "未知公式（根据结构推断）")
    result.setdefault("domain", "未确定")
    result.setdefault("confidence", "medium")
    result.setdefault("purpose", "")
    result.setdefault("intuition", "")
    result.setdefault("read_order", [])
    result.setdefault("variables", [])
    result.setdefault("common_misunderstandings", [])
    result.setdefault("suggested_questions", [])
    # structure_layers / layers 双向兼容
    if "structure_layers" not in result and "layers" in result:
        result["structure_layers"] = result["layers"]
    result.setdefault("structure_layers", [])
    result.setdefault("concept_layers", [])
    # 旧前端仍读 overview / layers：若缺失则由新字段映射
    if not result.get("layers"):
        result["layers"] = result.get("structure_layers", [])
    if not result.get("overview"):
        parts = [p for p in (result.get("purpose"), result.get("intuition")) if p]
        result["overview"] = " ".join(parts)
    result.setdefault("accessible_summary", result.get("overview", ""))
    return result


# ---------------- 语言纯净检测（第四阶段：修复中英混杂） ----------------

# 允许出现在中文讲解里的英文词：单字母变量不限；多字母只放行标准数学记号/函数名。
_ALLOWED_EN_WORDS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "log", "ln", "lg", "exp", "lim", "max", "min", "sup", "inf", "mod", "det",
    "Var", "Cov", "Corr", "Std", "dim", "rank", "tr", "grad", "div", "curl",
    "dx", "dy", "dz", "dt", "LaTeX", "MathML", "OCR", "pH",
}

_EN_WORD = re.compile(r"[A-Za-z]{2,}")
_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")


# 已观测到的高频混杂词 → 中文替换表：模型偶发输出这些词时直接确定性替换，
# 不再依赖重试碰运气。表里没有的词仍会进入 language_warnings。
_EN_FIX_MAP = {
    "spread": "扩散",
    "stubborn": "顽固",
    "system": "系统",
    "smooth": "平滑",
    "pattern": "模式",
    "balance": "平衡",
}


def _fix_text(text: str) -> str:
    """把中文段落里已知的混杂英文词替换为中文；白名单与单字母变量放行。"""
    if not text or not _HAS_CJK.search(text):
        return text

    def repl(m: re.Match) -> str:
        word = m.group(0)
        if word in _ALLOWED_EN_WORDS or word.lower() in _ALLOWED_EN_WORDS:
            return word
        return _EN_FIX_MAP.get(word.lower(), word)

    return _EN_WORD.sub(repl, text)


def fix_language_mixing(explanation: dict) -> dict:
    """对讲解 JSON 的所有中文文本字段做确定性混杂词替换（在检测之前执行）。"""
    exp = explanation
    for key in ("formula_name", "purpose", "intuition", "accessible_summary", "overview"):
        if exp.get(key):
            exp[key] = _fix_text(exp[key])
    exp["read_order"] = [_fix_text(s) for s in exp.get("read_order", [])]
    for v in exp.get("variables", []):
        v["role"] = _fix_text(v.get("role", ""))
        v["meaning"] = _fix_text(v.get("meaning", ""))
    for key in ("structure_layers", "concept_layers", "layers"):
        for layer in exp.get(key) or []:
            layer["title"] = _fix_text(layer.get("title", ""))
            layer["content"] = _fix_text(layer.get("content", ""))
    exp["common_misunderstandings"] = [_fix_text(m) for m in exp.get("common_misunderstandings", [])]
    exp["suggested_questions"] = [_fix_text(q) for q in exp.get("suggested_questions", [])]
    return exp


def detect_language_warnings(explanation: dict) -> list[str]:
    """检测中文讲解段落里夹杂的普通英文单词，返回警告列表（空=干净）。

    只查有中文的文本段（纯英文字段如变量符号不管）；单字母视为变量名放行；
    白名单内的数学记号/函数名放行；其余多字母英文词记入警告。
    """
    warnings: list[str] = []

    def check(field: str, text: str) -> None:
        if not text or not _HAS_CJK.search(text):
            return
        for word in _EN_WORD.findall(text):
            if word in _ALLOWED_EN_WORDS or word.lower() in _ALLOWED_EN_WORDS:
                continue
            warnings.append(f"{field}：夹杂英文词「{word}」")

    exp = explanation
    check("formula_name", exp.get("formula_name", ""))
    check("purpose", exp.get("purpose", ""))
    check("intuition", exp.get("intuition", ""))
    check("accessible_summary", exp.get("accessible_summary", ""))
    for i, step in enumerate(exp.get("read_order", [])):
        check(f"read_order[{i}]", step)
    for i, v in enumerate(exp.get("variables", [])):
        check(f"variables[{i}].role", v.get("role", ""))
        check(f"variables[{i}].meaning", v.get("meaning", ""))
    for key in ("structure_layers", "concept_layers"):
        for i, layer in enumerate(exp.get(key) or []):
            check(f"{key}[{i}].title", layer.get("title", ""))
            check(f"{key}[{i}].content", layer.get("content", ""))
    for i, m in enumerate(exp.get("common_misunderstandings", [])):
        check(f"common_misunderstandings[{i}]", m)
    for i, q in enumerate(exp.get("suggested_questions", [])):
        check(f"suggested_questions[{i}]", q)
    return warnings


# ---------------- 自一致性校验（机器可查的事实断言，拦幻觉） ----------------

# 坐标：本地解析器对公式里“有哪些变量、有哪些结构”是确定性的；
# LLM 讲解里与之矛盾的断言（凭空变量、凭空结构）可以零成本拦下来。

# 不要求 LLM 必须讲解的符号：微分记号 d、自然常数 e、虚数单位 i 常作固定记号出现
_COVERAGE_EXEMPT = {"d", "e", "i"}

# 结构断言 → 公式里必须存在的证据（LaTeX 命令 / Unicode 符号 / 结构树角色）
_STRUCT_CLAIMS: list[tuple[tuple[str, ...], tuple[str, ...], set[str], str]] = [
    (("分数", "分子", "分母"), ("\\frac", "\\dfrac", "\\tfrac", "\\cfrac", "/"), {"fraction", "derivative"}, "分数"),
    (("根号", "平方根", "开方", "开根"), ("\\sqrt", "√"), {"sqrt", "root"}, "根号"),
    (("积分",), ("\\int", "\\iint", "\\oint", "∫", "∬", "∮"), set(), "积分"),
    (("求和", "累加", "连加"), ("\\sum", "∑"), set(), "求和"),
    (("矩阵", "行列式"), ("matrix", "\\det", "\\begin{vmatrix}"), {"matrix"}, "矩阵"),
]

_LETTER = re.compile(r"[A-Za-z\u0370-\u03ff]")  # 拉丁 + 希腊字母


def _collect_identifiers(tree: dict) -> set[str]:
    """收集结构树里的变量符号（identifier 叶子）。"""
    idents: set[str] = set()

    def visit(node: dict) -> None:
        if node.get("role") == "identifier":
            t = (node.get("text") or "").strip()
            if t:
                idents.add(t)
        for ch in node.get("children", []):
            visit(ch)

    visit(tree)
    return idents


def _collect_roles(tree: dict) -> set[str]:
    roles: set[str] = set()

    def visit(node: dict) -> None:
        roles.add(node.get("role", ""))
        for ch in node.get("children", []):
            visit(ch)

    visit(tree)
    return roles


def detect_consistency_warnings(latex: str, tree: dict, explanation: dict) -> list[str]:
    """把 LLM 讲解里可确定性验证的事实断言与本地解析结果交叉比对，返回警告列表。

    两类检查（纯本地、零成本）：
    1. 变量交叉：变量表里的符号必须真实出现在公式中（拦凭空变量的幻觉）；
       公式里的变量若漏讲则提示不完整（微分记号 d、常数 e/i 豁免）。
    2. 结构断言：结构层描述里提到“分数/根号/积分/求和/矩阵”时，公式里必须真有对应结构。
    """
    warnings: list[str] = []
    idents = _collect_identifiers(tree)
    ident_chars = {ch for t in idents for ch in t}

    # 1a. 变量表凭空检查：LLM 给出的符号至少要有一个字母真实出现在公式里
    for v in explanation.get("variables", []):
        symbol = (v.get("symbol") or "").strip()
        letters = _LETTER.findall(symbol)
        if not letters:
            continue  # 纯数字/纯符号不查
        if not any(ch in ident_chars or ch in latex for ch in letters):
            warnings.append(f"变量表中的「{symbol}」未在公式里出现，可能是讲解幻觉")

    # 1b. 覆盖检查：公式里的单字母变量漏讲（仅提示，不算事实错误）
    explained = "".join((v.get("symbol") or "") for v in explanation.get("variables", []))
    missing = sorted(
        t for t in idents
        if len(t) == 1 and t not in _COVERAGE_EXEMPT
        and t not in _ALLOWED_EN_WORDS and t not in explained
    )
    if missing:
        warnings.append(f"公式里的变量 {'、'.join(missing)} 未在变量表中说明，讲解可能不完整")

    # 2. 结构断言检查：只查结构层（结构描述是客观断言，误报最少）
    roles = _collect_roles(tree)
    struct_text = "".join(
        (layer.get("title", "") + layer.get("content", ""))
        for layer in explanation.get("structure_layers") or []
    )
    for words, markers, need_roles, label in _STRUCT_CLAIMS:
        if not any(w in struct_text for w in words):
            continue
        present = any(m in latex for m in markers) or bool(need_roles & roles)
        if not present:
            warnings.append(f"结构描述提到「{label}」，但公式里并没有这个结构，请谨慎参考")
    return warnings


# ---------------- 普通文本转 LaTeX（第四阶段：多入口输入） ----------------

# 无 Key 时的规则兜底：只覆盖最常见写法，转不了的原样保留交用户确认。
_TEXT2LATEX_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"sqrt\s*\(([^()]*)\)"), r"\\sqrt{\1}"),          # sqrt(...) -> \sqrt{...}
    (re.compile(r"\u00b1|\+-|\+/-"), r"\\pm "),                    # ± / +- / +/-
    (re.compile(r"\u00d7"), r"\\times "),
    (re.compile(r"\u00f7"), r"\\div "),
    (re.compile(r"\u221e"), r"\\infty "),
    (re.compile(r"\u03c0"), r"\\pi "),
    (re.compile(r"\u2264"), r"\\le "),
    (re.compile(r"\u2265"), r"\\ge "),
    (re.compile(r"\u2260"), r"\\ne "),
    (re.compile(r"\binfinity\b", re.IGNORECASE), r"\\infty "),
    (re.compile(r"\bintegral\b", re.IGNORECASE), r"\\int "),
]


def _rules_normalize(text: str) -> dict:
    """无 Key / 调用失败时的本地规则转换：只处理常见符号，一律 low 置信度。"""
    latex = text.strip()
    changed = False
    for pat, repl in _TEXT2LATEX_RULES:
        latex, n = pat.subn(repl, latex)
        changed = changed or n > 0
    # a/b 形式的简单分式不强转（括号优先级容易转错），保留原样让用户确认
    latex = re.sub(r"\s+", " ", latex).strip()
    notes = (
        "本地规则转换（未配置大模型或调用失败），只处理了根号、正负号等常见符号，请仔细检查。"
        if changed else
        "未识别到可转换的符号，已原样保留，请检查是否为合法 LaTeX。"
    )
    return {"latex": latex, "confidence": "low", "notes": notes, "source": "rules"}


def normalize_text(text: str) -> dict:
    """把普通公式文本/中文描述转成 LaTeX。有 Key 走大模型，否则规则兜底。"""
    if not config.llm_available():
        return _rules_normalize(text)
    try:
        raw = _chat(
            [
                {"role": "system", "content": NORMALIZE_SYSTEM},
                {"role": "user", "content": f"请把下面的公式文本转成 LaTeX：\n{text}"},
            ],
            temperature=0.1,
        )
        result = _extract_json(raw)
        latex = str(result.get("latex", "")).strip()
        conf = result.get("confidence", "low")
        if conf not in ("high", "medium", "low"):
            conf = "low"
        return {
            "latex": latex,
            "confidence": conf,
            "notes": str(result.get("notes", "")).strip() or "请确认识别结果后再分析。",
            "source": "llm",
        }
    except Exception:
        return _rules_normalize(text)


# ---------------- 对外接口 ----------------

def explain(latex: str, tree: dict, speech_text: str, context: str | None = None) -> dict:
    """生成分层中文解释。有 Key 走大模型，失败或无 Key 走规则兑底。

    context：公式所在页面的上下文文字（插件提取时顺带抓取），仅用于消歧义。
    """
    if not config.llm_available():
        result = _rules_explanation(latex, tree, speech_text)
        result["consistency_warnings"] = []
        return result

    user_parts = [f"LaTeX 公式：{latex}"]
    tpl = templates.detect_template(latex, tree)
    if tpl:
        user_parts.append("【领域知识锚点】\n" + templates.grounding_text(tpl))
    if context:
        user_parts.append(
            "【公式所在页面的上下文】\n" + context.strip()[:600]
            + "\n请结合上下文讲解：先点明公式在上下文里的位置与角色（如选择题的某个选项、例题条件），"
            + "再讲公式本身；若上下文涉及题目任务，围绕任务讲这个公式为什么值得注意，但不替用户做题、不直接报答案。"
            + "若上下文与公式本身冲突，以公式为准。"
        )
    user_parts.append(f"结构树（含节点编号）：\n{tree_outline(tree)}")
    user_parts.append(f"整体朗读文本：{speech_text}")
    user_parts.append("请按系统要求输出 JSON。若领域知识锚点与实际公式不符，以实际公式为准并降低置信度。")
    user_msg = "\n\n".join(user_parts)
    try:
        raw = _chat(
            [
                {"role": "system", "content": EXPLAIN_SYSTEM},
                {"role": "user", "content": user_msg},
            ]
        )
        result = _extract_json(raw)
        result = _ensure_schema(result, tree, speech_text)
        result = calibrate_confidence(latex, tpl, result)
        result = fix_language_mixing(result)
        result["language_warnings"] = detect_language_warnings(result)
        result["consistency_warnings"] = detect_consistency_warnings(latex, tree, result)
        result["source"] = "llm"
        return result
    except Exception as exc:
        fallback = _rules_explanation(latex, tree, speech_text)
        fallback["overview"] = f"大模型调用失败（{exc}），以下为本地规则解释。" + fallback["overview"]
        fallback["consistency_warnings"] = []
        return fallback


def ask(latex: str, tree: dict, question: str, node_text: str | None = None) -> dict:
    """针对公式（或其中某个节点）回答追问。"""
    if not config.llm_available():
        return {
            "answer": "当前未配置大模型 Key，暂时无法回答自由追问。"
            "你仍然可以使用结构树导航和朗读功能。配置 LLM_API_KEY 后即可开启追问。",
            "source": "rules",
        }

    focus = f"\n用户当前聚焦的子结构：{node_text}" if node_text else ""
    user_msg = (
        f"公式 LaTeX：{latex}\n"
        f"公式结构树：\n{tree_outline(tree)}{focus}\n\n"
        f"学生的追问：{question}"
    )
    try:
        answer = _chat(
            [
                {"role": "system", "content": ASK_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.4,
        )
        return {"answer": _fix_text(answer.strip()), "source": "llm"}
    except Exception as exc:
        return {"answer": f"回答失败：{exc}。请稍后重试。", "source": "error"}


# ---------------- 第五阶段：理科符号转译（转译模式） ----------------
# 规则来自真实视障用户（北辰）的 Accessibility Protocol 提示词清单。
# 目标与讲解模式完全相反：不讲解，只把读屏读不了的符号转成可读纯文本。

TRANSCRIBE_SYSTEM = """你是一份专业的符号转译工具：把用户输入的文本里读屏软件读不了的
理科符号（数学/物理/化学）转成读屏友好的 Unicode 纯文本，然后原样返回。

两条完全不能违背的铁律：
1. 不输出任何客套话、前言、结语（禁止“好的”“以下是”“我来帮你”等）。
2. 不输出任何解析、解释、标题；只返回被转译好的原文内容。

以及一条硬性约束：不解题、不改写、不增删内容；保留原文段落和题号结构，只动读屏不友好的符号。

转义规则（无障碍 Accessibility Protocol）：
- 绝对禁止 LaTeX（严禁 \\frac、\\sqrt 等任何反斜杠命令）。
- 分数：a/b；多项加括号 (x+1)/(x+2)；嵌套按 () -> [] -> {} 层级。
- 上标：简单次幂用 Unicode（x²、x³、xⁿ、eˣ）；复杂次幂用 ^(…)，如 2^(n-1)。
- 下标：严格用 Unicode 下标，禁止下划线：a₁、Sₙ、aₙ₊₁、v₀、Eₖ。
- 根号：√3、√(3x+1)（括号表示整体在根号下）；多次根号：3次√(x)、n次√(a+b)。
- 对数：底数用 Unicode 下标：log₂(x)、logₐ(x)、ln(x)、lg(x)。
- 极限：lim(x→0) f(x)；导数：f'(x)；定积分：积分(从a到b) f(x)dx。
- 集合与关系：{x | x>1}；∈、∉、⊆、∩、∪；区间 [-1, +∞)。
- 几何：∠A、△ABC、⊥、∥、⊙O；向量写中文：向量AB、向量a；模长 |a|。
- 化学式：数字用 Unicode 下标：H₂O、CO₂、H₂SO₄；离子用上标：Na⁺、Cl⁻、Cu²⁺、SO₄²⁻；
  反应式：2H₂ + O₂ = 2H₂O；可逆 ⇌；气体/沉淀 ↑↓；同位素写中文如碳-14。
- 物理：希腊字母保持原样（α、β、Δ、λ、μ、ρ）；单位 m/s²、cm³；变化量 Δt；
  温度 ℃、角度 30°。注意：裸写的 30 C 不确定是温度时不要乱改。
- 比较符：≤、≥、≠、±；省略号用 …… 或 ...。
- 中文与公式符号之间保留一个空格（如 函数 f(x) 的值），优化读屏断句。

你的输出就是转译后的文本本身，不要包裹代码块，不要加任何说明。"""

# 模型可能不听话：扫描输出里的客套话/解释标题/LaTeX，检出即报警
_CHATTER_PATTERNS = [
    re.compile(r"^\s*(好的|以下是|下面是|我来帮你|转译结果如下|希望对你有帮助)[^\n]*[：:。]?", re.M),
    re.compile(r"^\s*(解析|解释|说明|分析|注意|总结|备注)\s*[：:]", re.M),
]
_LATEX_RESIDUE = re.compile(r"\\[a-zA-Z]+")


def _clean_transcription(text: str) -> tuple[str, list[str]]:
    """对转译输出做卫生处理：去代码块围栏/首尾客套行，检出不该有的东西。"""
    warnings: list[str] = []
    out = text.strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", out).strip()
        warnings.append("模型输出带代码块围栏，已自动去除。")
    for pat in _CHATTER_PATTERNS:
        if pat.search(out):
            warnings.append("检测到疑似客套话/解释性标题，请人工复核后再使用。")
            break
    if _LATEX_RESIDUE.search(out):
        warnings.append("输出中仍有 LaTeX 命令残留，转译可能不完整。")
    return out, warnings


# 结构性丢失哨兵：规则零命中零残留（medium）但文本带数学特征（LaTeX 命令、$…$、
# 上下标、分数、根号等记号）——说明规则把它拍平错了（如 KaTeX 视觉层文本），
# 宁可烧一次 LLM 额度也要兜底；普通中文文本不带这些特征，不会误触发
_MATH_SMELL_RE = re.compile(
    r"\\[a-zA-Z]|\$[^$]+\$|[⁰¹²³⁴⁵⁶⁷⁸⁹ⁿ]|[_^]\{|[×÷±≤≥≠∞∫∑√]|\d+\s*/\s*\d+"
)


def _suspicious_math(text: str, rule_result: dict) -> bool:
    """规则一条没命中（medium）却带着数学记号：大概率是结构性丢失，触发 LLM 兜底。"""
    return rule_result["confidence"] == "medium" and bool(_MATH_SMELL_RE.search(text))


def transcribe(text: str, engine: str | None = None, profile: str = "unicode_compact") -> dict:
    """理科符号转译主入口（第五阶段起，第六阶段接入树形解析）。

    三层兜底链：树形解析（真实语法，确定性）→ 正则管道（混排/化学/单位）
    → LLM（两条本地路线都盖不住的残余）。树路线只接管纯公式与定界符段，
    处理不了返回 None，行为对旧语料零回归。

    profile：unicode_compact=紧凑纯文本；spoken_structured=适合读屏连续朗读的结构稿。
    engine：None=自动；'rules' 强制本地（树优先+正则兜底，可离线可测试）；
    'llm' 强制走大模型。
    """
    from . import transcriber, tree_transcript  # 延迟导入，避免循环

    text = (text or "").strip()
    if not text:
        return {"ok": False, "error": "没有可转译的文本。"}

    forced = (engine or "").lower()
    profile = profile if profile in ("unicode_compact", "spoken_structured") else "unicode_compact"

    # 第一层：树形解析。纯公式/$…$ 段走真实语法树，语义规则（撇号=导数等）
    # 在树节点上局部生效；混排/解析失败时返回 None 自然降级。确定性、零额度。
    if forced != "llm":
        tree_out = tree_transcript.try_transcribe(text, profile=profile)
        if tree_out:
            return {
                "ok": True,
                "transcribed_text": tree_out["transcribed_text"],
                "confidence": "high",
                "source": "tree",
                "applied": tree_out["applied"],
                "residue": tree_out["residue"],
                "warnings": [],
            }

    if forced == "rules" or not config.llm_available():
        r = transcriber.rule_transcribe(text, profile=profile)
        warnings: list[str] = []
        if forced == "llm" and not config.llm_available():
            warnings.append("AI 重新转译当前不可用：未配置 LLM_API_KEY 或服务不可用，已返回本地规则结果。")
        if r["residue"]:
            warnings.append(
                "以下内容规则未能自动转换，请人工核对：" + "、".join(r["residue"]) + "。"
                + ("" if config.llm_available() else "配置 LLM_API_KEY 后可提升复杂内容的转译能力。")
            )
        return {
            "ok": True,
            "transcribed_text": r["transcribed_text"],
            "confidence": r["confidence"],
            "source": "rules",
            "applied": r["applied"],
            "residue": r["residue"],
            "warnings": warnings,
        }

    rule_result = transcriber.rule_transcribe(text, profile=profile)
    if forced == "llm" or rule_result["residue"] or _suspicious_math(text, rule_result):
        # 规则覆盖不住（或有强制要求）：走 LLM，规则结果作失败兜底
        try:
            profile_hint = (
                "本次请输出适合读屏连续朗读的结构稿，例如把积分、指数、上下限的视觉结构说清楚。"
                if profile == "spoken_structured"
                else "本次请输出紧凑 Unicode 纯文本，优先保留数学表达式形态。"
            )
            raw = _chat(
                [
                    {"role": "system", "content": TRANSCRIBE_SYSTEM},
                    {"role": "user", "content": profile_hint + "\n\n原文：\n" + text},
                ],
                temperature=0,
            )
            out, warnings = _clean_transcription(raw)
            return {
                "ok": True,
                "transcribed_text": out,
                "confidence": "high" if not warnings else "medium",
                "source": "llm",
                "applied": [],
                "residue": [],
                "warnings": warnings,
            }
        except Exception as exc:
            warnings = [f"大模型转译失败（{exc}），已回退本地规则，复杂符号可能未转净。"]
            if rule_result["residue"]:
                warnings.append("规则未覆盖的记号：" + "、".join(rule_result["residue"]) + "。")
            return {
                "ok": True,
                "transcribed_text": rule_result["transcribed_text"],
                "confidence": "medium",
                "source": "rules",
                "applied": rule_result["applied"],
                "residue": rule_result["residue"],
                "warnings": warnings,
            }

    # 规则已覆盖：直接返回，零 LLM 成本、确定性可复现
    return {
        "ok": True,
        "transcribed_text": rule_result["transcribed_text"],
        "confidence": rule_result["confidence"],
        "source": "rules",
        "applied": rule_result["applied"],
        "residue": rule_result["residue"],
        "warnings": [],
    }
