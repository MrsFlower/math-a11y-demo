# -*- coding: utf-8 -*-
"""重新触发一次自愈授权请求（清掉旧挂起对话框），供 UIA 点击「允许」。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
EXT = "nnhjbbjogdfgnipomcmogkoimopnkbaj"


def targets():
    return json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=5).read())


async def main():
    for t in targets():
        if t["url"] == f"chrome-extension://{EXT}/sidepanel.html" and t["type"] == "page":
            try:
                urllib.request.urlopen(f"{CDP}/json/close/{t['id']}", timeout=5)
                print("closed old sidepanel")
            except Exception as e:
                print("close err", e)
    await asyncio.sleep(1)
    req = urllib.request.Request(f"{CDP}/json/new?chrome-extension://{EXT}/sidepanel.html", method="PUT")
    urllib.request.urlopen(req, timeout=5)
    await asyncio.sleep(3)
    ctx = [t for t in targets() if t["url"] == f"chrome-extension://{EXT}/sidepanel.html" and t["type"] == "page"][0]
    js = r"""(async () => {
      extractPage();
      await new Promise(r => setTimeout(r, 1500));
      const b = document.getElementById('auth-grant-btn');
      if (b.hidden) return 'btn-hidden';
      b.click();
      return 'requested';
    })()"""
    async with websockets.connect(ctx["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": js, "awaitPromise": True,
                                             "returnByValue": True, "userGesture": True}}))
        while True:
            d = json.loads(await ws.recv())
            if d.get("id") == 1:
                print("触发结果:", d.get("result", {}).get("result", {}).get("value"))
                break


if __name__ == "__main__":
    asyncio.run(main())
