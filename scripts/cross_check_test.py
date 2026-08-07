# -*- coding: utf-8 -*-
"""双模型互查（第 5 层防线）：同一批公式分别用两个模型独立讲解，比对核心结论。

原理：两个独立模型对「这是什么公式、属于什么领域」意见一致时，讲解大概率可信；
意见分歧的公式就是需要人工重点复核的高风险样例。不进实时链路（成本×2、延迟×2），
作为离线抽样质检工具使用。

用法（需 .env 里有 LLM_API_KEY）：
    python scripts/cross_check_test.py                # 默认抽 6 条，用备用链前两个模型
    python scripts/cross_check_test.py --sample 10
    python scripts/cross_check_test.py --models qwen3.7-plus qwen-flash

输出：控制台报告 + eval_cases/latest_cross_check.md
退出码：0=一致率达标（>=80%），1=一致率过低或运行失败。
"""
import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import config, llm  # noqa: E402
from app.parser import python_engine  # noqa: E402

CASES_FILE = BASE_DIR / "eval_cases" / "formulas.json"
REPORT_FILE = BASE_DIR / "eval_cases" / "latest_cross_check.md"


def run_one_model(model: str, latex: str, tree: dict, speech: str) -> dict:
    """强制只用指定模型跑一次讲解（临时改写备用链，跑完恢复）。"""
    saved_models, saved_idx = config.LLM_MODELS, llm._model_idx
    config.LLM_MODELS = [model]
    llm._model_idx = 0
    try:
        return llm.explain(latex, tree, speech)
    finally:
        config.LLM_MODELS = saved_models
        llm._model_idx = saved_idx


def pick_cases(cases: list[dict], n: int) -> list[dict]:
    """等距抽样：覆盖文件头尾各领域，而不是只抽前 n 条。"""
    if n >= len(cases):
        return cases
    step = len(cases) / n
    return [cases[int(i * step)] for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser(description="双模型互查抽样质检")
    ap.add_argument("--sample", type=int, default=6, help="抽样条数（默认 6）")
    ap.add_argument("--models", nargs=2, default=None, metavar=("M1", "M2"),
                    help="两个互查模型（默认取备用链前两个）")
    args = ap.parse_args()

    if not config.llm_available():
        print("未配置 LLM_API_KEY，无法互查。")
        return 1
    models = args.models or config.LLM_MODELS[:2]
    if len(models) < 2:
        print(f"备用链只有 {len(models)} 个模型，无法互查。请用 --models 指定两个。")
        return 1

    cases = pick_cases(json.loads(CASES_FILE.read_text(encoding="utf-8")), args.sample)
    print(f"互查模型：{models[0]} vs {models[1]}，抽样 {len(cases)} 条\n")

    rows, agree_cnt = [], 0
    for c in cases:
        latex = c["latex"]
        try:
            base = python_engine.parse_latex(latex)
        except ValueError as exc:
            print(f"[跳过] {c['id']} 解析失败：{exc}")
            continue
        results = []
        for m in models:
            exp = run_one_model(m, latex, base["tree"], base["speech_text"])
            if exp.get("source") != "llm":
                print(f"[失败] {c['id']} 模型 {m} 未走 LLM（{exp.get('source')}），本条作废")
                results = []
                break
            results.append(exp)
        if len(results) != 2:
            continue

        names = [r.get("formula_name", "") for r in results]
        domains = [r.get("domain", "") for r in results]
        confs = [r.get("confidence", "") for r in results]
        # 名称判一致用宽松规则：一方名称包含另一方即可（“质能方程”vs“爱因斯坦质能方程”）
        name_agree = bool(names[0] and names[1]) and (names[0] in names[1] or names[1] in names[0])
        domain_agree = domains[0] == domains[1]
        agree = name_agree and domain_agree
        agree_cnt += agree
        mark = "一致" if agree else "**分歧**"
        rows.append(
            f"| {c['id']} | `{latex}` | {names[0]}（{domains[0]}/{confs[0]}） "
            f"| {names[1]}（{domains[1]}/{confs[1]}） | {mark} |"
        )
        print(f"[{'OK' if agree else '!!'}] {c['id']}: {names[0]}({domains[0]}) vs {names[1]}({domains[1]})")

    if not rows:
        print("没有成功完成互查的样例。")
        return 1
    rate = agree_cnt / len(rows)
    report = "\n".join([
        "# 双模型互查报告",
        "",
        f"- 模型：`{models[0]}` vs `{models[1]}`",
        f"- 样例：{len(rows)} 条，一致 {agree_cnt} 条，一致率 **{rate:.0%}**",
        "- 判定规则：公式名称一方包含另一方 且 领域完全相同 → 一致；分歧样例需人工复核。",
        "",
        f"| 样例 | LaTeX | {models[0]} | {models[1]} | 判定 |",
        "| --- | --- | --- | --- | --- |",
        *rows,
        "",
    ])
    REPORT_FILE.write_text(report, encoding="utf-8")
    print(f"\n一致率 {rate:.0%}（{agree_cnt}/{len(rows)}），报告已写入 {REPORT_FILE}")
    if rate < 0.8:
        print("一致率低于 80%，讲解质量可能有系统性问题，请人工复核分歧样例。")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
