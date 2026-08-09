# -*- coding: utf-8 -*-
"""复现：测试页场景3，选中含公式图的区域，走 background.js readSelection 同款逻辑。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
PAGE_URL = "http://127.0.0.1:8321/static/plugin_test_page.html"

# 选中第 3 节（含 img 的 section），然后跑 readSelection 同款逻辑
SELECT_SECTION3_AND_READ = r"""(function(){
  var sec = null;
  var secs = document.querySelectorAll('section');
  for (var i = 0; i < secs.length; i++) {
    if (secs[i].textContent.indexOf('维基百科公式图') >= 0) { sec = secs[i]; break; }
  }
  if (!sec) return { error: 'no section 3' };
  var sel = window.getSelection();
  var saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  sel.removeAllRanges();
  var r0 = document.createRange();
  r0.selectNodeContents(sec);
  sel.addRange(r0);

  // ===== 与 background.js readSelection 同款 =====
  var holder = document.createElement("div");
  holder.appendChild(sel.getRangeAt(0).cloneContents());
  var texOf = function (root) {
    var ann = root.querySelector('annotation[encoding="application/x-tex"]');
    if (ann && ann.textContent.trim()) return ann.textContent.trim();
    var scr = root.querySelector('script[type*="math"]');
    if (scr && scr.textContent.trim()) return scr.textContent.trim();
    return "";
  };
  holder.querySelectorAll(".katex, mjx-container, .MathJax_Display, .MathJax").forEach(function (el) {
    if (!holder.contains(el)) return;
    var tex = texOf(el);
    if (tex) el.replaceWith(document.createTextNode(" $" + tex + "$ "));
  });
  holder.querySelectorAll("math").forEach(function (m) {
    if (!holder.contains(m)) return;
    var alt = m.getAttribute("alttext");
    if (alt) m.replaceWith(document.createTextNode(" $" + alt + "$ "));
  });
  holder.querySelectorAll("img.mwe-math-fallback-image-inline, img.mwe-math-fallback-image-display").forEach(function (img) {
    if (!holder.contains(img)) return;
    var alt2 = (img.getAttribute("alt") || "").trim();
    if (alt2) img.replaceWith(document.createTextNode(" $" + alt2 + "$ "));
  });
  var result = (holder.textContent || "").replace(/\s+/g, " ").trim();
  var imgCount = holder.querySelectorAll("img").length;

  sel.removeAllRanges();
  if (saved) sel.addRange(saved);
  return { result: result, imgCount: imgCount };
})()"""


async def main() -> int:
    try:
        target = json.loads(urllib.request.urlopen(
            urllib.request.Request(f"{CDP}/json/new?{PAGE_URL}", method="PUT"), timeout=10).read())
    except Exception:
        target = json.loads(urllib.request.urlopen(f"{CDP}/json/new?{PAGE_URL}", timeout=10).read())
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
        r = await send("Runtime.evaluate", {"expression": SELECT_SECTION3_AND_READ, "returnByValue": True})
        v = (r.get("result", {}).get("result") or {}).get("value") or {}
        print("选中第3节后 readSelection 输出:", repr(v.get("result")))
        print("选区内残留 img 数:", v.get("imgCount"))
        print("结论:", "修复有效——选区路径拿到 E = mc^2" if "mc^2" in (v.get("result") or "") or "mc" in (v.get("result") or "") else "仍丢失")
    urllib.request.urlopen(urllib.request.Request(f"{CDP}/json/close/{tab_id}", method="GET"), timeout=10)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
