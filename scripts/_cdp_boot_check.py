# -*- coding: utf-8 -*-
"""CDP 验证：热重载插件后，侧边栏开机自检不再误报「无法连接」。"""
import asyncio
import json
import urllib.request

import websockets

EXT = r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\extension"


async def main():
    ws = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(ws, origin=None, max_size=20 * 1024 * 1024) as w:
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

        r = await call("Extensions.loadUnpacked", {"path": EXT})
        ext_id = r["result"]["id"]
        r = await call("Target.createTarget", {"url": f"chrome-extension://{ext_id}/sidepanel.html"})
        tid = r["result"]["targetId"]
        r = await call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sess = r["result"]["sessionId"]
        await asyncio.sleep(3)
        expr = "document.getElementById('status-line') ? document.getElementById('status-line').textContent : document.body.innerText.slice(0,300)"
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sess)
        print("侧边栏开机状态:", r["result"]["result"]["value"])
        expr2 = "fetch(apiBase() + '/api/health', {headers: authHeaders()}).then(function(x){return x.status;})"
        r = await call("Runtime.evaluate", {"expression": expr2, "awaitPromise": True, "returnByValue": True}, sess)
        print("带token健康检查状态码:", r["result"]["result"]["value"])
        await call("Target.closeTarget", {"targetId": tid})


asyncio.run(main())
