# -*- coding: utf-8 -*-
"""录制准备：加载插件 → 打开练习页 → 尝试程序化打开真实侧边栏。"""
import asyncio
import json
import urllib.request

import websockets

EXT = r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\extension"
PRACTICE = "http://127.0.0.1:8321/static/plugin_test_page.html"


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
        print("扩展已加载:", ext_id)

        r = await call("Target.createTarget", {"url": PRACTICE})
        tab_tid = r["result"]["targetId"]
        print("练习页已打开:", tab_tid)

        # 直接创建 service worker target 唤醒它
        r = await call(
            "Target.createTarget", {"url": f"chrome-extension://{ext_id}/background.js"}
        )
        await asyncio.sleep(1)
        r = await call("Target.getTargets")
        sw = None
        for t in r["result"]["targetInfos"]:
            if t["type"] == "service_worker" and ext_id in t.get("url", ""):
                sw = t
        if not sw:
            print("未找到 service worker")
            return
        r = await call("Target.attachToTarget", {"targetId": sw["targetId"], "flatten": True})
        sw_sess = r["result"]["sessionId"]

        # 拿 windowId：从练习页 target 取
        windows = await call("Browser.getWindowForTarget", {"targetId": tab_tid})
        wid = windows["result"]["windowId"]
        print("windowId:", wid)

        # 方案1：sidePanel.open（需用户手势，可能失败）
        expr = (
            "chrome.sidePanel.open({windowId: %d}).then(()=> 'panel-opened').catch(e=>'ERR:'+e.message)"
            % wid
        )
        r = await call(
            "Runtime.evaluate",
            {"expression": expr, "awaitPromise": True, "returnByValue": True},
            sw_sess,
        )
        print("sidePanel.open 结果:", r["result"]["result"].get("value"))

        # 方案2：模拟点击工具栏图标（openPopup，需 Chrome 127+）
        expr2 = "chrome.action.openPopup ? chrome.action.openPopup().then(()=>'popup-opened').catch(e=>'ERR2:'+e.message) : 'no-openPopup-api'"
        r = await call(
            "Runtime.evaluate",
            {"expression": expr2, "awaitPromise": True, "returnByValue": True},
            sw_sess,
        )
        print("action.openPopup 结果:", r["result"]["result"].get("value"))

        await asyncio.sleep(2)
        r = await call("Target.getTargets")
        found = False
        for t in r["result"]["targetInfos"]:
            if t["type"] == "side_panel":
                print("发现侧边栏 target:", t["targetId"], t["url"])
                found = True
        if not found:
            print("未发现侧边栏 target（录制时需人工按 Ctrl+Shift+M 打开）")


asyncio.run(main())
