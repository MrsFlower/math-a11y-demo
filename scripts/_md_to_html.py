# -*- coding: utf-8 -*-
"""参赛项目说明.md → 精排 HTML（供 Edge 无头打印 PDF）。
用法：python scripts/_md_to_html.py
"""
import sys
from pathlib import Path

import markdown

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
MD_FILE = ROOT / "docs" / "参赛项目说明.md"
OUT = ROOT / "dist" / "参赛项目说明.html"

text = MD_FILE.read_text(encoding="utf-8")
body = markdown.markdown(
    text,
    extensions=["tables", "fenced_code", "toc", "sane_lists"],
)

CSS = """
@page { size: A4; margin: 20mm 18mm; }
* { box-sizing: border-box; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
  font-size: 10.5pt; line-height: 1.75; color: #1a1a1a;
  max-width: 100%; margin: 0;
}
h1 { font-size: 20pt; text-align: center; margin: 0 0 4pt; letter-spacing: 1px; }
h2 {
  font-size: 14pt; margin: 22pt 0 8pt; padding: 4pt 8pt;
  background: #f0f4ff; border-left: 5px solid #2b5bd7;
  page-break-after: avoid;
}
h3 { font-size: 11.5pt; margin: 14pt 0 6pt; page-break-after: avoid; }
p { margin: 6pt 0; text-align: justify; }
blockquote {
  margin: 10pt 0; padding: 8pt 14pt; background: #fff7e6;
  border-left: 4px solid #f0a500; color: #5c4300;
}
blockquote p { margin: 2pt 0; }
table {
  border-collapse: collapse; width: 100%; margin: 8pt 0;
  font-size: 9.5pt; page-break-inside: avoid;
}
th, td { border: 1px solid #c9d4e8; padding: 4pt 7pt; text-align: left; vertical-align: top; }
th { background: #eef2fb; }
pre {
  background: #f6f8fa; border: 1px solid #e1e4e8; border-radius: 4px;
  padding: 8pt 10pt; font-size: 9pt; line-height: 1.5; overflow-x: hidden;
  white-space: pre-wrap; page-break-inside: avoid;
}
code { font-family: Consolas, "Courier New", monospace; }
p code, li code, td code { background: #f2f3f5; padding: 0 3px; border-radius: 3px; font-size: 9.5pt; }
ul, ol { margin: 4pt 0; padding-left: 22pt; }
li { margin: 2pt 0; }
strong { color: #14307a; }
hr { border: none; border-top: 1px solid #d0d7e2; margin: 14pt 0; }
em { color: #666; }
"""

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>数学公式无障碍学习助手 · 项目说明文档</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>
"""

OUT.parent.mkdir(exist_ok=True)
OUT.write_text(html, encoding="utf-8")
print(f"written: {OUT}")
