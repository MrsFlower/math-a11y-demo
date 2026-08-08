# -*- coding: utf-8 -*-
"""参赛项目说明 Markdown → 样式化 HTML → Edge 无头打印 PDF。"""
import subprocess
import sys
from pathlib import Path

from markdown import markdown

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "参赛项目说明.md"
HTML = ROOT / "dist" / "参赛项目说明.html"
PDF = ROOT / "dist" / "参赛项目说明.pdf"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

CSS = """
@page { margin: 2cm 1.8cm; }
body {
  font-family: "Microsoft YaHei", "微软雅黑", sans-serif;
  font-size: 11pt; line-height: 1.75; color: #1a1a1a; max-width: 100%;
}
h1 { font-size: 21pt; margin: 0 0 4pt; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; border-bottom: 1px solid #ddd; padding-bottom: 3pt; }
h3 { font-size: 12pt; margin: 12pt 0 4pt; }
blockquote {
  margin: 8pt 0; padding: 6pt 12pt; background: #f5f7fa;
  border-left: 4px solid #3b6fd4; color: #333;
}
code {
  font-family: Consolas, monospace; background: #f2f2f2;
  padding: 1pt 4pt; border-radius: 3px; font-size: 10pt;
}
pre {
  background: #f7f7f7; border: 1px solid #e3e3e3; border-radius: 4px;
  padding: 8pt 10pt; font-size: 9.5pt; line-height: 1.5; white-space: pre-wrap;
}
pre code { background: none; padding: 0; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; }
th, td { border: 1px solid #ccc; padding: 4pt 8pt; text-align: left; font-size: 10pt; }
th { background: #f0f3f8; }
hr { border: none; border-top: 1px solid #ddd; margin: 14pt 0; }
"""


def main():
    text = SRC.read_text(encoding="utf-8")
    body = markdown(text, extensions=["tables", "fenced_code"])
    html = (
        "<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<title>数学公式无障碍学习助手 · 参赛项目说明</title>"
        f"<style>{CSS}</style></head><body>{body}</body></html>"
    )
    HTML.parent.mkdir(parents=True, exist_ok=True)
    HTML.write_text(html, encoding="utf-8")
    cmd = [
        EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
        f"--print-to-pdf={PDF}", HTML.as_uri(),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    size = PDF.stat().st_size
    print(f"PDF 已生成：{PDF}（{size / 1024:.0f} KB）")


if __name__ == "__main__":
    main()
