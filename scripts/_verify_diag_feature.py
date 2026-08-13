# -*- coding: utf-8 -*-
"""验证 v0.8.0 诊断功能：重载扩展后，在 sidepanel 上下文点「运行诊断」，
分别在普通页与受限页抓取诊断报告，确认新 UI 与错误分类生效。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
EXT_ID = "nnhjbbjogdfgnipomcmogkoimopnkbaj"

_probe_id = 0


def http_json(method: str, url: str):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


async def browser_eval(ws_url: str, expr: str):
    global _probe_id
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        _probe_id += 1
        mid = _probe_id
        await ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            d = json.loads(await ws.recv())
            if d.get("id") == mid:
                return d


JS_RUN_DIAG = r"""
(async () => {
  const out = {};
  out.uiReady = !!(document.getElementById("diag-run-btn") && document.getElementById("diag-box") && document.getElementById("diag-output") && document.getElementById("diag-copy-btn"));
  out.version = chrome.runtime.getManifest().version;
  if (!out.uiReady || typeof runDiagnosis !== "function") return JSON.stringify(out);
  document.getElementById("diag-run-btn").click();
  // 等诊断跑完（健康检查最多 10 秒超时）
  for (let i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 500));
    if (!document.getElementById("diag-box").hidden) break;
  }
  out.report = document.getElementById("diag-output").value;
  return JSON.stringify(out);
})()
"""


async def main() -> int:
    ver = http_json("GET", f"{CDP}/json/version")
    # 1) 重载扩展，让新代码生效
    r = await browser_eval(ver["webSocketDebuggerUrl"],
                           f"Extensions.reloadExtension('{EXT_ID}')")
    print("重载扩展:", json.dumps(r.get("result", {}), ensure_ascii=False)[:200])
    await asyncio.sleep(2)

    # 2) 打开新 sidepanel 页（重载后旧页面失效）
    ctx = None
    for _try in range(3):
        try:
            http_json("PUT", f"{CDP}/json/new?chrome-extension://{EXT_ID}/sidepanel.html")
        except Exception:
            pass
        await asyncio.sleep(2)
        for t in http_json("GET", f"{CDP}/json/list"):
            if t["url"] == f"chrome-extension://{EXT_ID}/sidepanel.html" and t["type"] == "page":
                ctx = t
        if ctx:
            break
    if not ctx:
        print("找不到 sidepanel 页上下文")
        return 1
    await asyncio.sleep(3)  # 等 init() 完成

    # 3) 场景一：普通页（example.com 设为当前活动标签）→ 诊断应报「注入成功」
    async with websockets.connect(ctx["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        msg_id = 0

        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                d = json.loads(await ws.recv())
                if d.get("id") == msg_id:
                    return d

        await send("Runtime.evaluate", {"expression": r"""
        (async () => {
          let t = await chrome.tabs.create({ url: "https://example.com", active: true });
          await new Promise(r => setTimeout(r, 1500));
          return t.id;
        })()""", "awaitPromise": True, "returnByValue": True})

        r1 = await send("Runtime.evaluate", {"expression": JS_RUN_DIAG, "awaitPromise": True, "returnByValue": True})
        v1 = r1.get("result", {}).get("result", {}).get("value")
        d1 = json.loads(v1) if v1 else {}
        print("=== 场景一：普通网页 ===")
        print(f"UI 就绪={d1.get('uiReady')}  版本={d1.get('version')}")
        print(d1.get("report") or "(无报告)")

        # 4) 场景二：受限页 edge://settings → 诊断应报内置页面分类
        await send("Runtime.evaluate", {"expression": r"""
        (async () => {
          let t = await chrome.tabs.create({ url: "edge://settings", active: true });
          await new Promise(r => setTimeout(r, 1500));
          return t.id;
        })()""", "awaitPromise": True, "returnByValue": True})

        r2 = await send("Runtime.evaluate", {"expression": JS_RUN_DIAG, "awaitPromise": True, "returnByValue": True})
        v2 = r2.get("result", {}).get("result", {}).get("value")
        d2 = json.loads(v2) if v2 else {}
        print("\n=== 场景二：edge://settings ===")
        print(f"UI 就绪={d2.get('uiReady')}  版本={d2.get('version')}")
        print(d2.get("report") or "(无报告)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
