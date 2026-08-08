# -*- coding: utf-8 -*-
"""双层快捷键排查：
- 页面层：练习页装 keydown 监听，看按键是否到达网页；
- 扩展层：SW 装 chrome.commands 监听，看 Chrome 是否把命令路由给扩展。
运行后按 3 次 Ctrl+Shift+M，脚本每 5 秒打印两层状态，60 秒后结束。
"""
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
        targets = r["result"]["targetInfos"]

        # 1. 页面层：练习页 keydown 监听
        page = next((t for t in targets if t["type"] == "page" and "plugin_test_page" in t.get("url", "")), None)
        page_sess = None
        if page:
            r = await call("Target.attachToTarget", {"targetId": page["targetId"], "flatten": True})
            page_sess = r["result"]["sessionId"]
            expr = (
                "(function(){"
                "if(!window.__keySpy){window.__keySpy=true;window.__keyLog=[];"
                "document.addEventListener('keydown',function(e){"
                "window.__keyLog.push((e.ctrlKey?'Ctrl+':'')+(e.altKey?'Alt+':'')+(e.shiftKey?'Shift+':'')+e.key);"
                "},true);}"
                "return 'page-spy-ok';})()"
            )
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, page_sess)
            print("[页面层] 监听器:", r["result"]["result"].get("value"))
        else:
            print("!! 练习页没开着")

        # 2. 扩展层：SW 命令监听（先唤醒 SW）
        ext_id = "nnhjbbjogdfgnipomcmogkoimopnkbaj"
        dummy = await call("Target.createTarget",
                           {"url": f"chrome-extension://{ext_id}/background.js"})
        sw = None
        for _ in range(8):
            await asyncio.sleep(1)
            r = await call("Target.getTargets")
            sw = next((t for t in r["result"]["targetInfos"]
                       if t["type"] == "service_worker" and ext_id in t.get("url", "")), None)
            if sw:
                break
        await call("Target.closeTarget", {"targetId": dummy["result"]["targetId"]})
        sw_sess = None
        if sw:
            r = await call("Target.attachToTarget", {"targetId": sw["targetId"], "flatten": True})
            sw_sess = r["result"]["sessionId"]
            expr = (
                "(function(){"
                "if(!self.__cmdSpy){self.__cmdSpy=true;self.__cmdLog=[];"
                "chrome.commands.onCommand.addListener(function(cmd){"
                "self.__cmdLog.push(cmd+' @ '+new Date().toLocaleTimeString());});}"
                "return 'sw-spy-ok';})()"
            )
            r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sw_sess)
            print("[扩展层] 监听器:", r["result"]["result"].get("value"))
        else:
            print("!! SW 未唤醒")

        print("=== 现在点击练习页正文确保焦点在页面上，然后按 3 次 Ctrl+Shift+M ===")
        for i in range(12):
            await asyncio.sleep(5)
            if page_sess:
                r = await call("Runtime.evaluate",
                               {"expression": "JSON.stringify(window.__keyLog||[])", "returnByValue": True}, page_sess)
                print(f"[{(i+1)*5:>3}s] 页面层按键:", r["result"]["result"].get("value"))
            if sw_sess:
                r = await call("Runtime.evaluate",
                               {"expression": "JSON.stringify(self.__cmdLog||[])", "returnByValue": True}, sw_sess)
                print(f"[{(i+1)*5:>3}s] 扩展层命令:", r["result"]["result"].get("value"))
                r = await call("Runtime.evaluate",
                               {"expression": "chrome.storage.local.get('__shortcut_debug').then(o=>JSON.stringify(o.__shortcut_debug||null))",
                                "awaitPromise": True, "returnByValue": True}, sw_sess)
                print(f"      埋点数据:", r["result"]["result"].get("value"))


asyncio.run(main())
