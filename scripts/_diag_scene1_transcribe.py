# -*- coding: utf-8 -*-
"""复现场景1：选中 KaTeX 区域，跑 background.js readSelection 同款逻辑，再送后端转译。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
PAGE_URL = "http://127.0.0.1:8321/static/plugin_test_page.html"
API = "https://highcodzteceggb-azvgiimdkb.cn-beijing.fcapp.run"
TOKEN = "YOUR_FC_TRIGGER_TOKEN"

SELECT_SECTION1_AND_READ = r"""(function(){
  var sec = null;
  var secs = document.querySelectorAll('section');
  for (var i = 0; i < secs.length; i++) {
    if (secs[i].textContent.indexOf('KaTeX') >= 0) { sec = secs[i]; break; }
  }
  if (!sec) return { error: 'no section 1' };
  var sel = window.getSelection();
  var saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  sel.removeAllRanges();
  var r0 = document.createRange();
  r0.selectNodeContents(sec);
  sel.addRange(r0);

  // ===== 与 background.js readSelection 完全同款 =====
  var holder = document.createElement("div");
  holder.appendChild(sel.getRangeAt(0).cloneContents());
  var BLOCKS = ["P","LI","DIV","UL","OL","TR","BR","H1","H2","H3","H4","SECTION","ARTICLE","BLOCKQUOTE","PRE"];
  holder.querySelectorAll("*").forEach(function (n) {
    if (BLOCKS.indexOf(n.tagName) >= 0) n.insertAdjacentText("afterend", "\n");
  });
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
    else el.querySelectorAll(".katex-mathml, mjx-assistive-mml, annotation").forEach(function (n) { n.remove(); });
  });
  holder.querySelectorAll("math").forEach(function (m) {
    if (!holder.contains(m)) return;
    var alt = m.getAttribute("alttext");
    if (alt) m.replaceWith(document.createTextNode(" $" + alt + "$ "));
    else m.querySelectorAll("mjx-assistive-mml, annotation").forEach(function (n) { n.remove(); });
  });
  holder.querySelectorAll("img.mwe-math-fallback-image-inline, img.mwe-math-fallback-image-display").forEach(function (img) {
    if (!holder.contains(img)) return;
    var alt2 = (img.getAttribute("alt") || "").trim();
    if (alt2) img.replaceWith(document.createTextNode(" $" + alt2 + "$ "));
  });
  var result = (holder.textContent || "")
    .split("\n").map(function (s) { return s.replace(/\s+/g, " ").trim(); })
    .filter(Boolean).join("\n");

  sel.removeAllRanges();
  if (saved) sel.addRange(saved);
  return { result: result };
})()"""


async def main() -> int:
    try:
        target = json.loads(urllib.request.urlopen(
            urllib.request.Request(f"{CDP}/json/new?{PAGE_URL}", method="PUT"), timeout=10).read())
    except Exception:
        target = json.loads(urllib.request.urlopen(f"{CDP}/json/new?{PAGE_URL}", timeout=10).read())
    tab_id = target["id"]
    sel_text = ""
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
        r = await send("Runtime.evaluate", {"expression": SELECT_SECTION1_AND_READ, "returnByValue": True})
        sel_text = ((r.get("result", {}).get("result") or {}).get("value") or {}).get("result", "")
        print("readSelection 输出:", repr(sel_text))
    urllib.request.urlopen(urllib.request.Request(f"{CDP}/json/close/{tab_id}", method="GET"), timeout=10)

    # 送后端转译（与插件相同请求）
    req = urllib.request.Request(
        f"{API}/api/transcribe-symbols",
        data=json.dumps({"text": sel_text, "source_type": "selection",
                         "profile": "spoken_structured"}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    print("转译结果:", repr(data.get("transcribed_text")))
    print("confidence:", data.get("confidence"), " warnings:", data.get("warnings"))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
