# -*- coding: utf-8 -*-
"""验证 LaTeX 函数名规则：强制 rules 引擎，确认不再落 LLM 兜底。"""
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
time.sleep(2)

SAMPLES = [
    r"是 $\sin^2 x$ 的（ ）。",
    r"$f(x) = \ln(1 + x^2)$",
    r"$\arctan(e^x)$",
    r"$y' + \frac{1}{x}y = x$",
    r"$\lim_{x \to 0} \frac{x - \sin x}{x^2 \ln(1+x)}$",
]

for text in SAMPLES:
    body = json.dumps({"text": text, "profile": "spoken_structured", "engine": "rules"}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8321/api/transcribe-symbols",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=90) as r:
        d = json.loads(r.read().decode("utf-8"))
    print("in :", text)
    print("out:", d.get("transcribed_text"))
    print("residue:", d.get("residue"))
    print()
