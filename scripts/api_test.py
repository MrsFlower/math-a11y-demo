# -*- coding: utf-8 -*-
"""API 验收测试：对照任务文档验收标准逐项检查。用法：先启动服务，再 python scripts/api_test.py [port]"""
import io
import json
import sys

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
args = [a for a in sys.argv[1:] if a]
FAST = "--fast" in args
ports = [a for a in args if not a.startswith("--")]
PORT = ports[0] if ports else "8321"
BASE = f"http://127.0.0.1:{PORT}"
if FAST:
    print("[快速模式] 仅测本地规则/结构接口，不逐例调用大模型（with_explanation=false）。")

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {detail}" if detail else ""))


# 1. 健康检查
r = httpx.get(f"{BASE}/api/health", timeout=30).json()
check("health 接口", r.get("ok") is True, json.dumps(r, ensure_ascii=False))

# 2. 示例接口
r = httpx.get(f"{BASE}/api/examples", timeout=30).json()
check("内置示例 >= 3 个", len(r.get("examples", [])) >= 3)
examples = r["examples"]

# 3. 首页
r = httpx.get(BASE, timeout=30)
check("首页可访问且为 HTML", r.status_code == 200 and "数学公式无障碍" in r.text)

# 4. 验收指定公式 + 3 个内置示例，检查 JSON 字段完整
required_keys = ["latex", "mathml", "tree", "speech_text", "explanation", "plain_text"]
targets = [("验收公式", r"\int_{-\infty}^{\infty} f(x)e^{-i\omega x} dx")] + [
    (ex["title"], ex["latex"]) for ex in examples
]
for title, latex in targets:
    payload = {"latex": latex}
    if FAST:
        payload["with_explanation"] = False  # 快速模式：不调 LLM，只验证结构/服务链路
    r = httpx.post(f"{BASE}/api/parse-latex", json=payload, timeout=120).json()
    ok = r.get("ok") and all(k in r for k in required_keys)
    exp = r.get("explanation", {})
    ok = ok and "overview" in exp and "layers" in exp and "suggested_questions" in exp
    check(f"parse-latex：{title}", ok, f"来源={exp.get('source')}，层数={len(exp.get('layers', []))}")

# 5. 引擎切换与对比
r = httpx.post(f"{BASE}/api/parse-latex", json={"latex": r"\frac{1}{2}", "engine": "sre"}, timeout=120).json()
check("engine=sre 请求不报错（可回退）", r.get("ok") is True, r.get("engine", "") + str(r.get("engine_note", "")))
r = httpx.post(f"{BASE}/api/compare", json={"latex": r"\frac{1}{2}"}, timeout=120).json()
check("compare 双路线接口", r.get("ok") and "python_route" in r and "sre_route" in r)

# 6. 追问接口（无 Key 时应返回引导文案而不是崩溃）
r = httpx.post(
    f"{BASE}/api/ask",
    json={"latex": r"\frac{a}{b}", "question": "分母是什么意思？", "node_id": "n2"},
    timeout=120,
).json()
check("ask 追问接口", r.get("ok") is True and bool(r.get("answer")), f"来源={r.get('source')}")

# 7. 错误处理：非法 LaTeX 返回结构化错误
r = httpx.post(f"{BASE}/api/parse-latex", json={"latex": r"\frac{1}{"}, timeout=60)
body = r.json()
check("非法 LaTeX 返回 ok=false", body.get("ok") is False and bool(body.get("error")))

# 8. 空输入
r = httpx.post(f"{BASE}/api/parse-latex", json={"latex": "   "}, timeout=60).json()
check("空输入返回 ok=false", r.get("ok") is False)

# 9. OCR 接口（未配 Key 时应给出可读错误而非 500）
r = httpx.post(f"{BASE}/api/ocr-formula", files={"image": ("t.png", b"\x89PNG\r\n\x1a\nfake", "image/png")}, timeout=60)
check("ocr-formula 无Key时结构化报错", r.status_code in (400, 422) and r.json().get("ok") is False,
      r.json().get("error", "")[:60])

print("\n===== 结果：%d 通过 / %d 失败 =====" % (len(passed), len(failed)))
sys.exit(1 if failed else 0)
