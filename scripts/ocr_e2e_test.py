# -*- coding: utf-8 -*-
"""OCR 链路端到端测试：用 matplotlib 渲染公式图片 -> /api/ocr-formula -> /api/parse-latex"""
import io
import sys

import httpx
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
PORT = sys.argv[1] if len(sys.argv) > 1 else "8321"
BASE = f"http://127.0.0.1:{PORT}"

CASES = [
    ("求根公式", r"$x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}$"),
    ("傅里叶积分", r"$F(\omega)=\int_{-\infty}^{\infty} f(x)e^{-i\omega x}\,dx$"),
    ("勾股定理", r"$a^2 + b^2 = c^2$"),
]


def render(tex: str) -> bytes:
    fig = plt.figure(figsize=(4, 1.2), dpi=200)
    fig.text(0.5, 0.5, tex, ha="center", va="center", fontsize=18)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


for title, tex in CASES:
    png = render(tex)
    r = httpx.post(
        f"{BASE}/api/ocr-formula",
        files={"image": ("formula.png", png, "image/png")},
        timeout=180,
    ).json()
    print(f"\n=== {title} ===")
    print("原始 LaTeX:", tex.strip("$"))
    if not r.get("ok"):
        print("OCR 失败:", r.get("error"))
        continue
    print("识别 LaTeX:", r["latex"], f"（后端 {r.get('backend')}）")
    # 识别结果再走解析，验证端到端可用
    p = httpx.post(f"{BASE}/api/parse-latex", json={"latex": r["latex"]}, timeout=180).json()
    print("再解析:", "成功，朗读=" + p["speech_text"][:60] + "…" if p.get("ok") else "失败 " + str(p.get("error")))
