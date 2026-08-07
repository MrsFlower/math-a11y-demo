# -*- coding: utf-8 -*-
"""批量质量评估：读取 eval_cases/formulas.json，逐条调 /api/parse-latex，
生成 Markdown 报告到 eval_cases/latest_eval_report.md。

用法：python scripts/eval_formula_set.py [port]   # 默认 8321

退出码：
  0 = 全部样例有结果，且无「保守性红线」违规（avoid_overclaim=true 却 confidence=high）
  1 = 存在红线违规或请求失败样例

判定规则只做粗检（帮助快速发现坏样例），最终质量判断以人工评分表为准。
"""
import io
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "eval_cases" / "formulas.json"
REPORT_FILE = ROOT / "eval_cases" / "latest_eval_report.md"

PORT = sys.argv[1] if len(sys.argv) > 1 else "8321"
BASE = f"http://127.0.0.1:{PORT}"

# 过强断言词：出现在 purpose/intuition 且样例标记上下文不足时视为风险
_OVERCLAIM_PATTERNS = [r"这就是[^，。]{0,12}(定理|公式|定律)", r"著名的", r"毫无疑问", r"一定是"]


def full_text(exp: dict) -> str:
    """把讲解的所有文字拼成一段，用于关键词检索。"""
    parts = [
        exp.get("formula_name", ""), exp.get("purpose", ""), exp.get("intuition", ""),
        exp.get("accessible_summary", ""),
    ]
    for v in exp.get("variables", []):
        parts += [v.get("role", ""), v.get("meaning", "")]
    for layer in (exp.get("structure_layers") or []) + (exp.get("concept_layers") or []):
        parts += [layer.get("title", ""), layer.get("content", "")]
    parts += exp.get("common_misunderstandings", [])
    return "".join(parts)


def check_overclaim(case: dict, exp: dict) -> list[str]:
    """过度自信粗检，返回风险描述列表（空=无风险）。"""
    risks = []
    if not case.get("avoid_overclaim"):
        return risks
    conf = exp.get("confidence", "")
    name = exp.get("formula_name", "")
    if conf == "high":
        risks.append(f"红线：avoid_overclaim 样例 confidence=high")
    if not any(w in name for w in ("推断", "未知", "可能")):
        risks.append(f"公式名过于确定：「{name}」未含 推断/未知/可能")
    text = (exp.get("purpose", "") or "") + (exp.get("intuition", "") or "")
    for pat in _OVERCLAIM_PATTERNS:
        m = re.search(pat, text)
        if m:
            risks.append(f"过强断言：「{m.group(0)}」")
    return risks


def main() -> int:
    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    print(f"共 {len(cases)} 条样例，目标 {BASE}，开始评估（每条约 20 秒）…")

    rows = []       # 摘要表
    details = []    # 逐条详情
    n_fail = 0      # 请求失败数
    n_redline = 0   # 保守性红线违规数
    n_risky = 0     # 有任意风险标记的样例数
    t0 = time.time()

    for i, case in enumerate(cases, 1):
        cid = case["id"]
        print(f"[{i:2}/{len(cases)}] {cid} …", end=" ")
        try:
            r = httpx.post(f"{BASE}/api/parse-latex", json={"latex": case["latex"]}, timeout=180)
            r.raise_for_status()
            data = r.json()
            assert data.get("ok"), data.get("error", "接口返回 ok=false")
        except Exception as exc:
            n_fail += 1
            print(f"请求失败：{exc}")
            rows.append((cid, case["title"], "-", "-", "-", "请求失败", "-", "是"))
            details.append(f"### {cid}：{case['title']}\n\n- **请求失败**：{exc}\n")
            continue

        exp = data.get("explanation", {})
        text = full_text(exp)
        hits = [kw for kw in case.get("expected_keywords", []) if kw in text]
        misses = [kw for kw in case.get("expected_keywords", []) if kw not in text]
        risks = check_overclaim(case, exp)
        if any(risk.startswith("红线") for risk in risks):
            n_redline += 1
        if risks or misses:
            n_risky += 1

        conf = exp.get("confidence", "?")
        kw_note = f"{len(hits)}/{len(hits) + len(misses)}"
        risk_note = "；".join(risks) if risks else "无"
        rows.append((
            cid, case["title"], exp.get("formula_name", "?"), exp.get("domain", "?"),
            conf, kw_note, exp.get("source", "?"), "是" if risks else "否",
        ))
        details.append("\n".join(filter(None, [
            f"### {cid}：{case['title']}",
            "",
            f"- 输入：`{case['latex']}`",
            f"- 公式名：{exp.get('formula_name', '?')}（领域：{exp.get('domain', '?')}；"
            f"置信度：{conf}；来源：{exp.get('source', '?')}）",
            f"- 用途：{exp.get('purpose', '')}",
            f"- 直觉：{exp.get('intuition', '')}",
            f"- 变量数：{len(exp.get('variables', []))}；概念层数：{len(exp.get('concept_layers', []))}",
            f"- 关键词命中：{kw_note}" + (f"（未命中：{'、'.join(misses)}）" if misses else ""),
            f"- 疑似过度自信：{risk_note}",
            f"- 无障碍总结：{exp.get('accessible_summary', '')}",
            f"- 样例备注：{case.get('notes', '')}",
            "",
        ])))
        print(f"conf={conf} 关键词 {kw_note} 风险 {'有' if risks else '无'}")

    elapsed = time.time() - t0

    # ---- 生成 Markdown 报告 ----
    lines = [
        "# 批量质量评估报告（自动生成，勿手改）",
        "",
        f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 样例数：{len(cases)}；请求失败：{n_fail}；有风险标记：{n_risky}；保守性红线违规：{n_redline}",
        f"- 总耗时：{elapsed / 60:.1f} 分钟",
        "",
        "> 「风险标记」含关键词未命中与过度自信粗检，供人工评审聚焦，不代表最终判定。",
        "> 人工评审请使用 manual_review_template.md。",
        "",
        "## 摘要表",
        "",
        "| ID | 标题 | 识别公式名 | 领域 | 置信度 | 关键词 | 来源 | 需人工复核 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c).replace("|", "\\|") for c in row) + " |")
    lines += ["", "## 逐条详情", ""]
    lines += details
    REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n报告已写入 {REPORT_FILE}")
    print(f"样例 {len(cases)}｜失败 {n_fail}｜风险 {n_risky}｜红线 {n_redline}｜耗时 {elapsed / 60:.1f} 分钟")
    if n_redline or n_fail:
        print("结果：存在红线违规或失败样例，请查看报告。")
        return 1
    print("结果：全部样例有结果，保守性红线全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
