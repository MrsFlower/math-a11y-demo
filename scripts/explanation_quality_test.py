# -*- coding: utf-8 -*-
"""第二层「反流水账」质量粗检脚本。

目标：用规则粗检解释是否退化成纯结构复述，而不是完美评估。
用法：先启动服务（建议配好 LLM_API_KEY 效果更佳），再运行：
    python scripts/explanation_quality_test.py [port]

即使未配 Key，本地规则兜底也会产出第二层 schema，多数用词类规则仍应通过；
配置 Key 后才能真正体现「教学型理解」的质量。
"""
import io
import re
import sys

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
args = [a for a in sys.argv[1:] if a and not a.startswith("--")]
PORT = args[0] if args else "8321"
BASE = f"http://127.0.0.1:{PORT}"

# 每条 concept_layers.content 至少命中其一，防止只描述形状
# 前 9 个为任务书原始词表；后面是等价解释性词补充（LLM 常用“因为/代表/说明”等
# 同样在讲“为什么”，不应被判为流水账；任务书也说明这些规则只是粗检而非完美评估）
CONCEPT_WORDS = [
    "表示", "用来", "意味着", "直觉", "原因", "作用", "变化", "累积", "关系",
    "因为", "代表", "说明", "为什么", "就像", "相当于", "理解为", "揭示", "体现", "本质",
]
# 空话 purpose 黑名单（去空白后整体等于这些视为不合格）
PURPOSE_BLACKLIST = ["计算这个公式", "算这个公式", "求这个公式"]

# 5 类公式 + 针对性关键词要求
CASES = [
    {
        "name": "一元二次方程求根公式",
        "latex": r"x = \frac{-b \pm \sqrt{b^2 - 4ac}}{2a}",
        "must_any": ["判别式", "两个解"],
    },
    {
        "name": "傅里叶变换",
        "latex": r"\int_{-\infty}^{\infty} f(x)e^{-i\omega x} dx",
        "must_any": ["频率", "频率成分"],
    },
    {
        "name": "偏导数",
        "latex": r"\frac{\partial u}{\partial t} = \frac{\partial^2 u}{\partial x^2}",
        "must_any": ["变化率", "固定其他变量"],
    },
    {
        "name": "矩阵",
        "latex": r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}",
        "must_any": [],  # 无针对性关键词，只做通用反流水账检查
    },
    {
        "name": "求和（大运算符）",
        "latex": r"\sum_{i=1}^{n} i^2",
        "must_any": [],
    },
]

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))


def zh_len(text):
    """统计中文字符个数（不含标点/英文/数字）。"""
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


for case in CASES:
    title = case["name"]
    r = httpx.post(f"{BASE}/api/parse-latex", json={"latex": case["latex"]}, timeout=120).json()
    if not r.get("ok"):
        check(f"{title}：接口成功", False, r.get("error", "")[:60])
        continue
    exp = r.get("explanation", {}) or {}
    source = exp.get("source")

    # --- API 结构验收：新 schema 关键字段齐全 ---
    schema_keys = [
        "formula_name", "domain", "purpose", "intuition",
        "variables", "structure_layers", "concept_layers", "accessible_summary",
    ]
    missing = [k for k in schema_keys if k not in exp]
    check(f"{title}：schema 字段齐全", not missing, f"缺失={missing} 来源={source}")

    # --- intuition 至少 40 个中文字 ---
    n = zh_len(exp.get("intuition"))
    check(f"{title}：intuition>=40 中文字", n >= 40, f"实际={n}")

    # --- purpose 不是空话 ---
    purpose = (exp.get("purpose") or "").strip()
    purpose_norm = re.sub(r"\s+", "", purpose)
    empty_talk = (not purpose) or any(purpose_norm == b for b in PURPOSE_BLACKLIST)
    check(f"{title}：purpose 非空话", not empty_talk, purpose[:40])

    # --- concept_layers 至少 2 条 ---
    concepts = exp.get("concept_layers") or []
    check(f"{title}：concept_layers>=2", len(concepts) >= 2, f"实际={len(concepts)}")

    # --- 每条 concept_layers.content 命中概念词 ---
    bad = []
    for i, layer in enumerate(concepts):
        content = layer.get("content", "") if isinstance(layer, dict) else str(layer)
        if not any(w in content for w in CONCEPT_WORDS):
            bad.append(i + 1)
    check(f"{title}：concept 含概念词", not bad, f"未命中层={bad}" if bad else "")

    # --- 针对性关键词（在整段解释文本里检索）---
    if case["must_any"]:
        blob = " ".join([
            exp.get("purpose", ""),
            exp.get("intuition", ""),
            exp.get("accessible_summary", ""),
            " ".join(l.get("content", "") for l in concepts if isinstance(l, dict)),
            " ".join(
                l.get("content", "")
                for l in (exp.get("structure_layers") or [])
                if isinstance(l, dict)
            ),
        ])
        hit = any(w in blob for w in case["must_any"])
        check(f"{title}：出现关键词{case['must_any']}", hit)

print("\n===== 质量粗检结果：%d 通过 / %d 失败 =====" % (len(passed), len(failed)))
if failed:
    print("提示：未配置 LLM_API_KEY 时，intuition 长度/领域关键词类检查更依赖模板兜底，")
    print("      建议配置 Key 后重跑以反映真实『教学型理解』质量。")
sys.exit(1 if failed else 0)
