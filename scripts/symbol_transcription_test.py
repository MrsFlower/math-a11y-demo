# -*- coding: utf-8 -*-
"""第五阶段：理科符号转译回归测试。

用法：
    python scripts/symbol_transcription_test.py 8321          # 默认走规则引擎（确定性、零额度消耗）
    python scripts/symbol_transcription_test.py https://example.com
    python scripts/symbol_transcription_test.py 8321 --llm    # 强制走大模型（慢、消耗免费额度）

检查项（对齐任务书）：
1. 接口返回 ok == true；
2. 输出不含 LaTeX 命令（\\frac、\\sqrt 等）；
3. 输出不含客套话（好的 / 下面是 / 我来帮你 等）；
4. 输出不含解释性标题（解析 / 说明 / 解释 等）；
5. 命中用例 expected 中的关键转译结果，且不出现 forbidden 内容。
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx

CASES_PATH = Path(__file__).resolve().parent.parent / "eval_cases" / "symbol_transcription_cases.json"

RE_LATEX = re.compile(r"\\[a-zA-Z]+")
RE_EXPLAIN_TITLE = re.compile(r"^\s*(解析|说明|解释|分析)\s*[：:]", re.M)
CHATTER_WORDS = ["好的", "下面是", "我来帮你", "以下是", "希望对您", "转译结果如下", "祝你"]


def check_output(text: str) -> list[str]:
    """返回该输出违反的铁律列表（空 = 干净）。"""
    problems = []
    m = RE_LATEX.search(text)
    if m:
        problems.append(f"含 LaTeX 命令残留：{m.group(0)}")
    m = RE_EXPLAIN_TITLE.search(text)
    if m:
        problems.append(f"含解释性标题：{m.group(0).strip()}")
    for w in CHATTER_WORDS:
        if w in text:
            problems.append(f"含客套话：{w}")
    return problems


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "8321"
    engine = "llm" if "--llm" in sys.argv else "rules"
    base = target.rstrip("/") if target.startswith(("http://", "https://")) else f"http://127.0.0.1:{target}"
    token = os.getenv("API_AUTH_TOKEN", "258697c6-125d-40d0-943d-38c7bb817b5a").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    print(f"转译测试：{len(cases)} 条用例，引擎 = {engine}，服务 = {base}")
    passed, failed = 0, 0
    for case in cases:
        reasons = []
        try:
            profile = case.get("profile", "unicode_compact")
            resp = httpx.post(
                f"{base}/api/transcribe-symbols",
                headers=headers,
                json={
                    "text": case["text"],
                    "source_type": "plain_text",
                    "engine": engine,
                    "profile": profile,
                },
                timeout=180,
            )
            data = resp.json()
        except Exception as exc:
            print(f"FAIL {case['id']}（{case['category']}）：请求异常 {exc}")
            failed += 1
            continue
        if not data.get("ok"):
            reasons.append(f"ok != true：{data.get('error')}")
        else:
            out = data.get("transcribed_text", "")
            reasons += check_output(out)
            for exp in case.get("expected", []):
                if exp not in out:
                    reasons.append(f"缺少期望片段：{exp}")
            for fb in case.get("forbidden", []):
                if fb in out:
                    reasons.append(f"出现禁止内容：{fb}")
        if reasons:
            failed += 1
            print(f"FAIL {case['id']}（{case['category']}）")
            for r in reasons:
                print(f"     - {r}")
            if data.get("ok"):
                print(f"     输出：{data.get('transcribed_text', '')[:120]}")
        else:
            passed += 1
            print(f"PASS {case['id']}（{case['category']}）")
    print(f"\n结果：{passed}/{len(cases)} 通过，{failed} 失败。")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
