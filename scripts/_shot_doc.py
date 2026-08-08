# -*- coding: utf-8 -*-
"""打开参赛项目说明 HTML 并截图，用于人工抽查排版。"""
import asyncio
import base64
import json
import urllib.request

import websockets

URL = r"file:///C:/Users/15866/Documents/codeheaven/小程序大赛/math-a11y-assistant/dist/参赛项目说明.html"
OUT = r"C:\Users\15866\AppData\Local\Temp\pdf_check.png"


async def main():
    ws = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(ws, origin=None, max_size=40 * 1024 * 1024) as w:
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

        r = await call("Target.createTarget", {"url": URL})
        tid = r["result"]["targetId"]
        r = await call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sess = r["result"]["sessionId"]
        await asyncio.sleep(2)
        r = await call("Page.captureScreenshot", {"format": "png"}, sess)
        with open(OUT, "wb") as f:
            f.write(base64.b64decode(r["result"]["data"]))
        print("截图已保存:", OUT)
        await call("Target.closeTarget", {"targetId": tid})


asyncio.run(main())
