# -*- coding: utf-8 -*-
"""读取 background.js 埋点的快捷键调试数据。"""
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
        sw = next((t for t in r["result"]["targetInfos"] if t["type"] == "service_worker"), None)
        if not sw:
            print("!! SW 不在运行")
            return
        r = await call("Target.attachToTarget", {"targetId": sw["targetId"], "flatten": True})
        sess = r["result"]["sessionId"]
        expr = "chrome.storage.local.get('__shortcut_debug').then(o => JSON.stringify(o.__shortcut_debug || null))"
        r = await call("Runtime.evaluate",
                       {"expression": expr, "awaitPromise": True, "returnByValue": True}, sess)
        print("__shortcut_debug =", r["result"]["result"].get("value"))


asyncio.run(main())
