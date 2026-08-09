# -*- coding: utf-8 -*-
"""验证：裸 getSelection().toString()（面板按钮路径）在场景1会拿到污染文本。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
import websockets

CDP = "http://127.0.0.1:9333"
PAGE_URL = "http://127.0.0.1:8321/static/plugin_test_page.html"

EXPR = r"""(function(){
  var secs = document.querySelectorAll('section');
  var sec = null;
  for (var i = 0; i < secs.length; i++) {
    if (secs[i].textContent.indexOf('KaTeX') >= 0) { sec = secs[i]; break; }
  }
  var sel = window.getSelection();
  sel.removeAllRanges();
  var r0 = document.createRange();
  r0.selectNodeContents(sec);
  sel.addRange(r0);
  var raw = sel.toString();
  sel.removeAllRanges();
  return raw;
})()"""


async def main() -> int:
    try:
        target = json.loads(urllib.request.urlopen(
            urllib.request.Request(f"{CDP}/json/new?{PAGE_URL}", method="PUT"), timeout=10).read())
    except Exception:
        target = json.loads(urllib.request.urlopen(f"{CDP}/json/new?{PAGE_URL}", timeout=10).read())
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
        r = await send("Runtime.evaluate", {"expression": EXPR, "returnByValue": True})
        raw = (r.get("result", {}).get("result") or {}).get("value", "")
        print("裸 toString 输出:", repr(raw))
        print("含隐藏层污染:", "是" if ("𝑥" in raw or "𝑏" in raw) else "否")
    urllib.request.urlopen(urllib.request.Request(f"{CDP}/json/close/{target['id']}", method="GET"), timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
