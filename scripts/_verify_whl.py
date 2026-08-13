# -*- coding: utf-8 -*-
"""验证新 whl 内是否包含全部后端改动（用法：python scripts\\_verify_whl.py <whl路径>）。"""
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

whl = sys.argv[1] if len(sys.argv) > 1 else r"dist\math_a11y_assistant_6fcf16ce-0.1.0-py3-none-any.whl"
z = zipfile.ZipFile(whl)
src = z.read("app/transcriber.py").decode("utf-8")
llm = z.read("app/llm.py").decode("utf-8")
tree = z.read("app/tree_transcript.py").decode("utf-8")
engine = z.read("app/parser/python_engine.py").decode("utf-8")
main = z.read("app/main.py").decode("utf-8")

checks = {
    # 第六阶段：树优先三层兜底链（本轮）
    "tree_transcript.py 在包内": "try_transcribe" in tree,
    "llm.py 树优先接线": "tree_transcript" in llm,
    "撇号导数语义规则": "_prime_count" in engine,
    "lim 参数语义规则": "_FUNC_LIKE_OPS" in engine,
    "积分尾段合并": "_merge_diff_tail" in engine,
    "lim 参数紧凑箭头读法": 'arg = sub["text"].replace(" ", "")' in engine,
    # 兜底闭环
    "llm.py 返回 residue": '"residue":' in llm,
    "llm.py AI 不可用警告": "AI 重新转译当前不可用" in llm,
    # 高级 LaTeX 规则
    "矩阵/cases 解析": "bmatrix" in src and "_normalize_cases_body" in src,
    "配对扫描 _read_balanced": "_read_balanced" in src,
    # 极限下标回归守卫（lim 的 m 不能被当普通记号吃掉 _{...}）
    "命令名下标守卫": "属于命令自身" in src,
    # 历史修复回归
    "LaTeX函数名规则": "LaTeX函数名" in src,
    "_latex_lim 重写": "parts[0].strip()" in src,
    "二元减号允许空格": r"\s*-\s*" in src,
    "结构朗读分式": "_speak_fractions" in src,
    # 0.8.3：分式读法偏好（fraction_style 参数贯通）
    "树引擎分式风格分支": "_fraction_spoken" in engine and "FRACTION_STYLES" in engine,
    "main.py 接收 fraction_style": "fraction_style" in main,
}
for k, ok in checks.items():
    print(("PASS" if ok else "FAIL"), k)

names = [n for n in z.namelist() if n.startswith(("app/", "deploy_starter/", "static"))]
print("包内文件数:", len(z.namelist()))
sys.exit(0 if all(checks.values()) else 1)
