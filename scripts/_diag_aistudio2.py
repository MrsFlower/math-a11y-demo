# -*- coding: utf-8 -*-
"""AI Studio 复现第二步：模拟用户选中含公式的题目行，看插件能拿到什么文本，再送转译验证。
同时读取侧边栏 storage 里的快捷键调试/捕获痕迹。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
TAB_ID = "29DB2D5D7253CD90E7D82E587F908BA3"
SIDE_ID = "C945A242DD3C35FE02CF50AA82FED6E7"

SELECT_EXPR = r"""(function(){
  var out = {};
  // 找第一个包含 KaTeX 且有足够正文的块（模拟用户选中一道题）
  var els = document.querySelectorAll('p, li, div');
  var target = null;
  for (var i = 0; i < els.length; i++) {
    var el = els[i];
    if (!el.querySelector('.katex')) continue;
    var t = (el.innerText || '').replace(/\s+/g, ' ').trim();
    if (t.length >= 30 && t.length <= 600) { target = el; break; }
  }
  if (!target) { return { error: 'no katex block found' }; }
  out.tag = target.tagName + (target.className ? '.' + String(target.className).slice(0, 60) : '');
  var sel = window.getSelection();
  var saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  sel.removeAllRanges();
  var r = document.createRange();
  r.selectNodeContents(target);
  sel.addRange(r);
  out.selected_len = sel.toString().length;
  out.selected_text = sel.toString().slice(0, 400);
  // 恢复现场
  sel.removeAllRanges();
  if (saved) sel.addRange(saved);
  return out;
})()"""

STORAGE_EXPR = "chrome.storage.local.get(null).then(o => {" \
    "var keys = Object.keys(o).filter(k => k.indexOf('__') === 0 || k.indexOf('capture') >= 0 || k.indexOf('shortcut') >= 0);" \
    "var out = {}; keys.forEach(k => { try { out[k] = JSON.parse(JSON.stringify(o[k])); } catch(e) { out[k] = String(o[k]); } });" \
    "return out; })"


async def eval_target(tid, expr, await_promise=False):
    data = json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=10).read().decode("utf-8"))
    target = next((t for t in data if t.get("id") == tid), None)
    if not target:
        return {"error": f"target {tid} not found"}
    async with websockets.connect(target["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "id": 1, "method": "Runtime.evaluate",
            "params": {"expression": expr, "returnByValue": True, "awaitPromise": await_promise},
        }))
        while True:
            d = json.loads(await ws.recv())
            if d.get("id") == 1:
                return (d.get("result", {}).get("result") or {}).get("value") or d


def transcribe(text, profile):
    body = json.dumps({"text": text, "profile": profile}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8321/api/transcribe-symbols",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


async def main() -> int:
    print("== 模拟选中（含 KaTeX 的题目行）==")
    sel = await eval_target(TAB_ID, SELECT_EXPR)
    print(json.dumps(sel, ensure_ascii=False, indent=1))

    if isinstance(sel, dict) and sel.get("selected_text"):
        text = sel["selected_text"]
        for profile in ("unicode_compact", "spoken_structured"):
            try:
                d = transcribe(text, profile)
                print(f"\n== 转译 {profile} ==")
                print("输出:", d.get("transcribed_text", "")[:300])
            except Exception as e:
                print(f"\n== 转译 {profile} == 失败: {e}")

    print("\n== 侧边栏 storage 调试痕迹 ==")
    st = await eval_target(SIDE_ID, STORAGE_EXPR, await_promise=True)
    print(json.dumps(st, ensure_ascii=False, indent=1)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
