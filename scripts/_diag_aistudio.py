# -*- coding: utf-8 -*-
"""诊断 Google AI Studio 页面：公式 DOM / iframe / shadow DOM / 真实 content.js 提取结果。"""
import asyncio
import json
import pathlib
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CONTENT_JS = pathlib.Path(
    r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\extension\content.js"
).read_text(encoding="utf-8")

CDP = "http://127.0.0.1:9333"
TAB_ID = "29DB2D5D7253CD90E7D82E587F908BA3"

DIAG_EXPR = r"""(function(){
  var out = {};
  out.url = location.href;
  out.title = document.title;
  out.ready = document.readyState;
  // 公式相关 DOM 统计
  out.counts = {
    math: document.querySelectorAll('math').length,
    annotation: document.querySelectorAll('annotation[encoding]').length,
    script_tex: document.querySelectorAll('script[type*="math"]').length,
    katex: document.querySelectorAll('.katex').length,
    mjx: document.querySelectorAll('mjx-container').length,
    mathjax_display: document.querySelectorAll('.MathJax, .MathJax_Display').length,
    mwe_img: document.querySelectorAll('img.mwe-math-fallback-image-inline, img.mwe-math-fallback-image-display').length,
    iframe: document.querySelectorAll('iframe').length,
    pre: document.querySelectorAll('pre').length,
    code: document.querySelectorAll('code').length,
    editable: document.querySelectorAll('[contenteditable="true"], [contenteditable="plaintext-only"]').length
  };
  // iframe 的 src 与跨域情况
  out.iframes = [];
  document.querySelectorAll('iframe').forEach(function(f){
    var src = f.src || '';
    var cross = true;
    try { cross = !(f.contentDocument); } catch(e) { cross = true; }
    out.iframes.push({ src: src.slice(0, 120), cross_origin_blocked: cross });
  });
  // 浅层 shadow DOM 扫描（常见组件容器）
  var shadowHosts = 0, shadowMath = 0;
  document.querySelectorAll('*').forEach(function(el){
    if (el.shadowRoot) {
      shadowHosts++;
      shadowMath += el.shadowRoot.querySelectorAll('math, .katex, mjx-container, annotation').length;
    }
  });
  out.shadow = { hosts: shadowHosts, math_inside: shadowMath };
  // 正文里是否有数学记号（抽 body 文本）
  var bodyText = document.body ? (document.body.innerText || '') : '';
  out.body_len = bodyText.length;
  out.math_marks = [];
  var marks = /[\\$]|∫|√|±|≤|≥|∑|\bfrac\b|\bsqrt\(/g, m;
  var lines = bodyText.split('\n');
  for (var i = 0; i < lines.length && out.math_marks.length < 8; i++) {
    if (marks.test(lines[i])) { out.math_marks.push(lines[i].trim().slice(0, 100)); }
    marks.lastIndex = 0;
  }
  return out;
})()"""


async def main() -> int:
    data = json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=10).read().decode("utf-8"))
    target = next((t for t in data if t.get("id") == TAB_ID), None)
    if not target:
        print("找不到 AI Studio 标签页")
        return 1
    msg_id = 0
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                d = json.loads(await ws.recv())
                if d.get("id") == msg_id:
                    return d

        r = await send("Runtime.evaluate", {"expression": DIAG_EXPR, "returnByValue": True})
        info = (r.get("result", {}).get("result") or {}).get("value")
        print("== 页面基本信息 ==")
        print(json.dumps(info, ensure_ascii=False, indent=1))

        r2 = await send("Runtime.evaluate", {"expression": CONTENT_JS, "returnByValue": True})
        formulas = (r2.get("result", {}).get("result") or {}).get("value")
        print("\n== 真实 content.js 提取 ==")
        if formulas is None:
            print("提取出错:", json.dumps(r2, ensure_ascii=False)[:400])
        else:
            print(f"共 {len(formulas)} 条")
            for i, f in enumerate(formulas, 1):
                print(f"  {i}. [{f['kind']}] ({f['source']}) {f['latex'][:80]}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
