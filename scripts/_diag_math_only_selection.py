# -*- coding: utf-8 -*-
"""实证：只选中场景1左半（MathML 渲染体）时，selection_reader.js 能否保住根号。
同时回归：整 .katex 容器选中、整 section 选中两条路径。
页面用 file:// 打开（不依赖本机后端）。"""
import asyncio
import json
import os
import sys
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = "file:///" + urllib.parse.quote(
    os.path.join(ROOT, "static", "plugin_test_page.html").replace("\\", "/"))
READER = os.path.join(ROOT, "extension", "selection_reader.js")

CASES = {
    "只选左半 math 渲染体": "var m=document.querySelector('section .katex-mathml math');var r=document.createRange();r.selectNodeContents(m);",
    "整 .katex 容器": "var k=document.querySelector('section .katex');var r=document.createRange();r.selectNodeContents(k);",
    "整 section": "var s=document.querySelectorAll('section')[0];var r=document.createRange();r.selectNodeContents(s);",
}


async def main() -> int:
    reader_src = open(READER, encoding="utf-8").read()
    try:
        target = json.loads(urllib.request.urlopen(
            urllib.request.Request(f"{CDP}/json/new?{PAGE}", method="PUT"), timeout=10).read())
    except Exception:
        target = json.loads(urllib.request.urlopen(f"{CDP}/json/new?{PAGE}", timeout=10).read())
    tab_id = target["id"]
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        msg = 0

        async def send(method, params):
            nonlocal msg
            msg += 1
            await ws.send(json.dumps({"id": msg, "method": method, "params": params}))
            while True:
                d = json.loads(await ws.recv())
                if d.get("id") == msg:
                    return d

        await asyncio.sleep(1.5)
        for name, select_js in CASES.items():
            expr = (
                "(function(){var sel=window.getSelection();sel.removeAllRanges();"
                + select_js
                + "sel.addRange(r);return 1;})()"
            )
            await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            r = await send("Runtime.evaluate", {"expression": reader_src, "returnByValue": True})
            out = ((r.get("result", {}).get("result") or {}).get("value")) or ""
            print(f"== {name} ==")
            print(repr(out))
            print()
    urllib.request.urlopen(urllib.request.Request(f"{CDP}/json/close/{tab_id}", method="GET"), timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
