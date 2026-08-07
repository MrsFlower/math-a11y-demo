# -*- coding: utf-8 -*-
"""快速自测脚本：跑 3 个内置示例，验证解析引擎输出。用法：python scripts/smoke_test.py"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.examples import EXAMPLES
from app.parser import python_engine, sre_engine

for ex in EXAMPLES:
    print("=" * 60)
    print("示例：", ex["title"])
    print("LaTeX：", ex["latex"])
    try:
        result = python_engine.parse_latex(ex["latex"])
        print("[A 纯Python] 朗读：", result["speech_text"])
        print("[A 纯Python] 结构树：")
        print(python_engine.tree_outline(result["tree"]))
        sre_out = sre_engine.speak_mathml(result["mathml"])
        if sre_out.get("speech_text"):
            print(f"[B SRE(locale={sre_out['locale']})] 朗读：", sre_out["speech_text"])
        else:
            print("[B SRE] 不可用：", sre_out.get("error"))
    except Exception as exc:
        print("!! 失败：", exc)
        raise
print("=" * 60)
print("全部示例通过。")
