# -*- coding: utf-8 -*-
"""探测 chrome://extensions 的 shadow DOM 结构，找到开发者模式开关并打开。"""
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
        if not t:
            r = await call("Target.createTarget", {"url": "chrome://extensions/"})
            tid = r["result"]["targetId"]
            await asyncio.sleep(2.5)
        else:
            tid = t["targetId"]
        r = await call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sess = r["result"]["sessionId"]

        # 1. 先列出 manager shadowRoot 里的所有元素
        expr1 = (
            "(function(){"
            "var m=document.querySelector('extensions-manager');"
            "if(!m) return 'no-manager';"
            "var sr=m.shadowRoot;"
            "var tags=Array.from(sr.querySelectorAll('*')).map(function(e){"
            "return e.tagName.toLowerCase()+(e.id?'#'+e.id:'');"
            "});"
            "return tags.join(', ');"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr1, "returnByValue": True}, sess)
        print("manager shadowRoot 元素:", r["result"]["result"].get("value"))

        # 2. 找所有 toggle/cr-toggle 元素并检查 aria/label
        expr2 = (
            "(function(){"
            "var m=document.querySelector('extensions-manager');"
            "var sr=m.shadowRoot;"
            "var out=[];"
            "sr.querySelectorAll('cr-toggle, [role=switch], toggle').forEach(function(e){"
            "out.push({tag:e.tagName.toLowerCase(), id:e.id, label:e.getAttribute('aria-label')||e.getAttribute('label'), checked:e.checked});"
            "});"
            "var tb=sr.querySelector('#toolbar');"
            "if(tb&&tb.shadowRoot){"
            "tb.shadowRoot.querySelectorAll('cr-toggle, [role=switch]').forEach(function(e){"
            "out.push({tag:'toolbar>'+e.tagName.toLowerCase(), id:e.id, label:e.getAttribute('aria-label')||e.getAttribute('label'), checked:e.checked});"
            "});"
            "}"
            "return JSON.stringify(out,null,1);"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr2, "returnByValue": True}, sess)
        print("toggle 候选:", r["result"]["result"].get("value"))


asyncio.run(main())
