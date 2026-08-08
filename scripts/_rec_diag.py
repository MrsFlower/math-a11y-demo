# -*- coding: utf-8 -*-
"""诊断：唤醒 SW 并挂快捷键监听。
用法：手动重装/刷新扩展后跑本脚本，看到「spy-ok 等待按键」后按 Ctrl+Shift+M，
脚本会在 60 秒内打印是否收到命令。
"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

EXT_ID = "nnhjbbjogdfgnipomcmogkoimopnkbaj"


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

        # 1. 找扩展 id（万一重装后变了，从 chrome://extensions 页面兜底查一次）
        r = await call("Target.getTargets")
        ext_id = None
        for t in r["result"]["targetInfos"]:
            u = t.get("url", "")
            if u.startswith("chrome-extension://") and (
                    t["type"] == "service_worker" or "background.js" in u or "sidepanel.html" in u):
                ext_id = u.split("//")[1].split("/")[0]
                break

        # 2. 唤醒 SW
        if ext_id:
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
        else:
            sw = None

        if not sw:
            print("!! SW 仍未唤醒。请先在 chrome://extensions 手动刷新或重装扩展，再重跑本脚本。")
            return

        print("[OK] SW 已唤醒:", sw["url"][:70])
        r = await call("Target.attachToTarget", {"targetId": sw["targetId"], "flatten": True})
        sess = r["result"]["sessionId"]
        expr = (
            "(function(){"
            "if(!self.__cmdSpy){"
            "self.__cmdLog=[];self.__cmdSpy=true;"
            "chrome.commands.onCommand.addListener(function(cmd){"
            "self.__cmdLog.push(cmd+' @ '+new Date().toLocaleTimeString());});"
            "}"
            "return 'spy-ok';"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sess)
        print("监听器:", r["result"]["result"].get("value"))
        print("=== 现在按 Ctrl+Shift+M（焦点放在 Chrome 窗口），60 秒内我会报告结果 ===")
        for i in range(12):
            await asyncio.sleep(5)
            r = await call("Runtime.evaluate",
                           {"expression": "JSON.stringify(self.__cmdLog||[])", "returnByValue": True}, sess)
            log = r["result"]["result"].get("value")
            if log and log != "[]":
                print("[OK] 快捷键命令已收到:", log)
                return
            print(f"[..] 已等 {(i+1)*5} 秒，还没收到命令…")
        print("!! 60 秒内没收到命令。请检查 chrome://extensions/shortcuts 里本扩展的快捷键")
        print("   是否被清空，若是则点击输入框重新按 Ctrl+Shift+M 设置。")


asyncio.run(main())
