# -*- coding: utf-8 -*-
"""语言纯净度测试：验证中文讲解不夹杂普通英文单词（第四阶段第 9 项）。

用法：python scripts/language_quality_test.py [port]   # 默认 8321

对 4 条公式各调一次 /api/parse-latex，检查返回的 language_warnings：
- 为空 → 通过；
- 非空 → 同一条公式重试一次（LLM 输出有随机性），重试仍不干净才算失败。

退出码：0 = 全部通过；1 = 存在失败或请求错误。
"""
import io
import sys
import time

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

PORT = sys.argv[1] if len(sys.argv) > 1 else "8321"
BASE = f"http://127.0.0.1:{PORT}"

CASES = [
    ("热传导方程", r"\frac{\partial T}{\partial t} = \alpha \frac{\partial^2 T}{\partial x^2}"),
    ("牛顿第二定律", r"F = ma"),
    ("傅里叶变换", r"\int_{-\infty}^{\infty} f(x)e^{-i\omega x} dx"),
    ("贝叶斯公式", r"P(A|B) = \frac{P(B|A)P(A)}{P(B)}"),
]


def run_once(latex: str) -> tuple[list[str], str]:
    """请求一次，返回 (language_warnings, source)。请求失败时抛异常。"""
    r = httpx.post(f"{BASE}/api/parse-latex", json={"latex": latex}, timeout=180)
    r.raise_for_status()
    data = r.json()
    assert data.get("ok"), data.get("error", "接口返回 ok=false")
    exp = data.get("explanation", {})
    return exp.get("language_warnings", []), exp.get("source", "?")


def main() -> int:
    print(f"语言纯净度测试：{len(CASES)} 条公式，目标 {BASE}（每条约 20 秒，含重试最长约 3 分钟）")
    failed = 0
    t0 = time.time()

    for title, latex in CASES:
        print(f"\n== {title} ==")
        try:
            warnings, source = run_once(latex)
        except Exception as exc:
            print(f"[FAIL] 请求失败：{exc}")
            failed += 1
            continue

        if source != "llm":
            # 规则兜底文本是固定中文，不存在混杂问题，但要提示当前没测到大模型
            print(f"[SKIP] 解释来源为 {source}（非 llm），规则文本无混杂风险，跳过。")
            continue
        if not warnings:
            print("[OK ] 首次生成即无英文混杂。")
            continue

        print(f"[WARN] 首次生成检出 {len(warnings)} 处混杂，重试一次：")
        for w in warnings:
            print(f"       - {w}")
        try:
            warnings2, _ = run_once(latex)
        except Exception as exc:
            print(f"[FAIL] 重试请求失败：{exc}")
            failed += 1
            continue
        if not warnings2:
            print("[OK ] 重试后无英文混杂（首次为概率性输出）。")
        else:
            print(f"[FAIL] 重试后仍检出 {len(warnings2)} 处混杂：")
            for w in warnings2:
                print(f"       - {w}")
            failed += 1

    print(f"\n总计：{len(CASES) - failed} 通过 / {failed} 失败（耗时 {time.time() - t0:.0f} 秒）")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
