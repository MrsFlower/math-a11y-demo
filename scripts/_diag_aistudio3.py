# -*- coding: utf-8 -*-
"""AI Studio 验证：新版 readSelection 克隆替换逻辑 + 转译输出 + content.js 上下文质量。"""
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

# 与 background.js readSelection 的 func 完全同款逻辑，外加先选中一道题
SELECT_AND_READ = r"""(function(){
  var els = document.querySelectorAll('p, li, div');
  var target = null;
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    if (!el.querySelector('.katex')) continue;
    var t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (t.length >= 30 && t.length <= 600) { target = el; break; }
  }
  if (!target) return { error: 'no katex block' };
  var sel = window.getSelection();
  var saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  sel.removeAllRanges();
  var r0 = document.createRange();
  r0.selectNodeContents(target);
  sel.addRange(r0);

  // ===== 与 background.js 相同 =====
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
    if (tex) {
      el.replaceWith(document.createTextNode(" $" + tex + "$ "));
    } else {
      el.querySelectorAll(".katex-mathml, mjx-assistive-mml, annotation").forEach(function (n) { n.remove(); });
    }
  });
  holder.querySelectorAll("math").forEach(function (m) {
    if (!holder.contains(m)) return;
    var alt = m.getAttribute("alttext");
    if (alt) {
      m.replaceWith(document.createTextNode(" $" + alt + "$ "));
    } else {
      m.querySelectorAll("mjx-assistive-mml, annotation").forEach(function (n) { n.remove(); });
    }
  });
  var cleaned = (holder.textContent || "").split("\n").map(function (s) {
    return s.replace(/\s+/g, " ").trim();
  }).filter(Boolean).join("\n");
  // ===== 恢复现场 =====
  sel.removeAllRanges();
  if (saved) sel.addRange(saved);
  return { cleaned: cleaned };
})()"""


async def eval_tab(expr):
    data = json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=10).read().decode("utf-8"))
    target = next((t for t in data if t.get("id") == TAB_ID), None)
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
        out = {}
        r = await send("Runtime.evaluate", {"expression": SELECT_AND_READ, "returnByValue": True})
        out["select"] = (r.get("result", {}).get("result") or {}).get("value")
        r2 = await send("Runtime.evaluate", {"expression": CONTENT_JS, "returnByValue": True})
        out["formulas"] = (r2.get("result", {}).get("result") or {}).get("value")
        return out


def transcribe(text, profile):
    body = json.dumps({"text": text, "profile": profile}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8321/api/transcribe-symbols",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


async def main() -> int:
    res = await eval_tab(SELECT_AND_READ)
    cleaned = (res["select"] or {}).get("cleaned", "")
    print("== 新版选区读取 ==")
    print(cleaned[:400])
    if cleaned:
        d = transcribe(cleaned, "spoken_structured")
        print("\n== spoken_structured 转译 ==")
        print(d.get("transcribed_text", "")[:400])

    formulas = res["formulas"] or []
    print(f"\n== content.js 提取 {len(formulas)} 条，前 3 条的上下文 ==")
    for f in formulas[:3]:
        print("-", f["latex"][:50])
        print("  context:", (f.get("context") or "(空)")[:150])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
