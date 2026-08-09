# -*- coding: utf-8 -*-
"""验证新 whl 内 transcriber.py / llm.py 是否包含本轮全部后端改动。"""
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

whl = r"dist\math_a11y_assistant_6fcf16ce-0.1.0-py3-none-any.whl"
z = zipfile.ZipFile(whl)
src = z.read("app/transcriber.py").decode("utf-8")
llm = z.read("app/llm.py").decode("utf-8")

checks = {
    # 兜底闭环（本轮）
    "llm.py 返回 residue": '"residue":' in llm,
    "llm.py AI 不可用警告": "AI 重新转译当前不可用" in llm,
    # 新增高级 LaTeX 规则（本轮）
    "矩阵/cases 解析": "bmatrix" in src and "_normalize_cases_body" in src,
    "配对扫描 _read_balanced": "_read_balanced" in src,
    # 极限下标回归守卫（lim 的 m 不能被当普通记号吃掉 _{...}）
    "命令名下标守卫": "属于命令自身" in src,
    # 历史修复回归
    "LaTeX函数名规则": "LaTeX函数名" in src,
    "_latex_lim 重写": "parts[0].strip()" in src,
    "二元减号允许空格": r"\s*-\s*" in src,
    "结构朗读分式": "_speak_fractions" in src,
}
for k, ok in checks.items():
    print(("PASS" if ok else "FAIL"), k)

names = [n for n in z.namelist() if n.startswith(("app/", "deploy_starter/", "static"))]
print("包内文件数:", len(z.namelist()))
sys.exit(0 if all(checks.values()) else 1)
