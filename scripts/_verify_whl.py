# -*- coding: utf-8 -*-
"""验证新 whl 内 transcriber.py 是否包含本轮全部后端修复。"""
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

whl = r"dist\math_a11y_assistant_aa67882a-0.1.0-py3-none-any.whl"
z = zipfile.ZipFile(whl)
src = z.read("app/transcriber.py").decode("utf-8")

checks = {
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
