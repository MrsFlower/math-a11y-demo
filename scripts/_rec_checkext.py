# -*- coding: utf-8 -*-
"""检查扩展管理页与快捷键页的实际显示状态。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets


async def main():
    ws = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(ws, origin=None, max_size=10 * 1024 * 1024) as w:
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

        # 打开 chrome://extensions 看扩展状态
        r = await call("Target.createTarget", {"url": "chrome://extensions/"})
        tid = r["result"]["targetId"]
        await asyncio.sleep(2.5)
        r = await call("Target.attachToTarget", {"targetId": tid, "flatten": True})
        sess = r["result"]["sessionId"]
        expr = (
            "(function(){"
            "function deepText(root){var out=[];root.querySelectorAll('*').forEach(function(e){"
            "if(e.shadowRoot){out=out.concat(deepItems(e.shadowRoot));}"
            "});return out;}"
            "try{"
            "var m=document.querySelector('extensions-manager');"
            "var list=m.shadowRoot.querySelector('extensions-item-list');"
            "var items=list.shadowRoot.querySelectorAll('extensions-item');"
            "var out=[];"
            "items.forEach(function(it){"
            "var sr=it.shadowRoot;"
            "var name=sr.querySelector('#name');"
            "var toggle=sr.querySelector('#enableToggle');"
            "out.push({id:it.id, name:name?name.textContent.trim():'?', "
            "enabled:toggle?!toggle.checked:'?', toggleLabel:toggle?toggle.getAttribute('aria-label'):'?'});"
            "});"
            "return JSON.stringify(out,null,1);"
            "}catch(e){return 'err: '+e.message;}"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sess)
        print("=== chrome://extensions ===")
        print(r["result"]["result"].get("value"))

        # 跳到快捷键页
        await call("Page.navigate", {"url": "chrome://extensions/shortcuts"}, sess)
        await asyncio.sleep(2.5)
        expr2 = (
            "(function(){"
            "try{"
            "var sc=document.querySelector('extensions-shortcuts');"
            "if(!sc) return 'no extensions-shortcuts element; body children: '+Array.from(document.body.children).map(e=>e.tagName).join(',');"
            "var items=sc.shadowRoot.querySelectorAll('extension-command-view');"
            "var out=[];"
            "items.forEach(function(it){"
            "var sr=it.shadowRoot;"
            "var inp=sr.querySelector('cr-shortcut-input');"
            "out.push({ext:it.extensionName, desc:it.commandDescription, shortcut:inp?(inp.value||'(未设置)'):'no-input'});"
            "});"
            "return JSON.stringify(out,null,1);"
            "}catch(e){return 'err: '+e.message;}"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr2, "returnByValue": True}, sess)
        print("=== chrome://extensions/shortcuts ===")
        print(r["result"]["result"].get("value"))
        await call("Target.closeTarget", {"targetId": tid})


asyncio.run(main())
