# -*- coding: utf-8 -*-
"""测试转译模式（直接读）对教程类文章选区文本的处理效果。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE = "http://127.0.0.1:8321"

SAMPLES = {
    "腾讯云-代码块选区": (
        "# 常规写法 -- 省略大括号 -- 分子 \\over 分母\n"
        "# 建议还是使用常规写法\n"
        "分数: $\\frac{1}{2} + \\frac1x = {2 + x \\over 2x}$\n"
        "分数嵌套: $\\frac{1}{a + \\frac{2}{b}} = c$"
    ),
    "知乎-行间公式代码块选区": "\\[\n\\frac{1}{2}+\\frac{1}{3}=\\frac{5}{6}\n\\]",
    "知乎-正文段落选区": "其中\\int表示不定积分符号。",
}

for name, text in SAMPLES.items():
    body = json.dumps({"text": text, "profile": "spoken_structured"}).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/transcribe-symbols",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read().decode("utf-8"))
        print("===", name, "===")
        print("输入:", text.replace("\n", " ⏎ "))
        print("输出:", d.get("transcribed_text", ""))
        print("警告:", d.get("warnings") or d.get("notes") or "(无)")
        print()
    except Exception as e:
        print("===", name, "=== 失败:", e)
