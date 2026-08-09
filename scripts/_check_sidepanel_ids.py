# -*- coding: utf-8 -*-
"""交叉核对 sidepanel.js 引用的元素 id 是否都在 sidepanel.html 中定义。"""
import io
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

js = open(r"extension\sidepanel.js", encoding="utf-8").read()
html = open(r"extension\sidepanel.html", encoding="utf-8").read()

used = set(re.findall(r'\$\("([a-z0-9-]+)"\)', js))
defined = set(re.findall(r'id="([a-z0-9-]+)"', html))
# 动态创建的槽位（createElement / innerHTML）不算缺失
dynamic = {"history-slot"}

missing = sorted(used - defined - dynamic)
print("JS 引用但 HTML 缺失:", missing if missing else "无")
print("结果:", "OK" if not missing else "FAIL")
sys.exit(0 if not missing else 1)
