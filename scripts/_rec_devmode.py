# -*- coding: utf-8 -*-
"""自动打开 chrome://extensions 的开发者模式开关。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets


async def main():
    ws = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(ws, origin=None) as w:
        mid = 0

        async def call(method, params=None, sess=None):
            nonlocal mid
            mid += 1
            msg = {"id": mid, "method": method}
            if params:
                msg["params"] = params
            if sess:
                msg["sessionId"] = sess
            await w.send(json.dumps(msg))
            while True:
                r = json.loads(await w.recv())
                if r.get("id") == mid:
                    return r

        r = await call("Target.getTargets")
        t = next((x for x in r["result"]["targetInfos"] if "chrome://extensions" in x.get("url", "")), None)
        if t:
            tid = t["targetId"]
            await call("Page.navigate", {"url": "chrome://extensions/"}, None)
        else:
            r = await call("Target.createTarget", {"url": "chrome://extensions/"})
            tid = r["result"]["targetId"]
        await asyncio.sleep(2.5)
        r = await call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sess = r["result"]["sessionId"]
        expr = (
            "(function(){"
            "var m=document.querySelector('extensions-manager');"
            "if(!m) return 'no-manager url='+location.href;"
            "var tb=m.shadowRoot.querySelector('#devMode');"
            "if(!tb) return 'no-devMode-toggle';"
            "var before=tb.checked;"
            "if(!tb.checked) tb.click();"
            "return 'before='+before+' after='+tb.checked;"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sess)
        print("开发者模式:", r["result"]["result"].get("value"))


asyncio.run(main())
