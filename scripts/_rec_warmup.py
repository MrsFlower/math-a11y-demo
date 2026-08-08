# -*- coding: utf-8 -*-
"""录制预热：云端全链路各跑一遍 + 测试浏览器窗口调到录制状态。"""
import asyncio
import json
import time
import urllib.request

import websockets

BASE = "https://highcodpmiufnwj-cvgvqsopuz.cn-beijing.fcapp.run"
TOK = "6973c90b-ce3b-45c1-8c0b-7897f1797106"
HDRS = {"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"}


def post(path, payload, timeout=90):
    t0 = time.time()
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode(), headers=HDRS
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode())
    return time.time() - t0, data


def warm():
    print("== 云端预热 ==")
    dt, d = post("/api/transcribe-symbols", {"text": "∫f(x)e^(−iωx)dx", "profile": "spoken_structured"})
    print(f"转译 {dt:.1f}s ->", d.get("transcribed_text", "")[:40])
    dt, d = post("/api/explain", {"latex": "e^{i\\pi}+1=0"})
    print(f"讲解 {dt:.1f}s -> ok={d.get('ok')}, 字段:", list(d.get("explanation", d).keys())[:5] if isinstance(d.get("explanation", d), dict) else "text")
    dt, d = post("/api/ask", {"latex": "e^{i\\pi}+1=0", "question": "它为什么重要"})
    print(f"追问 {dt:.1f}s -> ok={d.get('ok')}")
    t0 = time.time()
    req = urllib.request.Request(BASE + "/api/tts", data=json.dumps({"text": "这就是数学之美。"}).encode(), headers=HDRS)
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    print(f"TTS {time.time() - t0:.1f}s -> {r.headers.get('Content-Type')}, {len(body) / 1024:.0f} KB 音频")


async def window_setup():
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

        r = await call("Target.getTargets")
        tab = None
        for t in r["result"]["targetInfos"]:
            if t["type"] == "page" and "plugin_test_page" in t.get("url", ""):
                tab = t
        if not tab:
            print("练习页 tab 未找到，跳过窗口设置")
            return
        r = await call("Browser.getWindowForTarget", {"targetId": tab["targetId"]})
        wid = r["result"]["windowId"]
        await call("Browser.setWindowBounds", {
            "windowId": wid, "bounds": {"windowState": "maximized"}
        })
        r = await call("Target.attachToTarget", {"targetId": tab["targetId"], "flatten": True})
        sess = r["result"]["sessionId"]
        # Ctrl + 加号两次：100% -> 110% -> 125%
        for _ in range(2):
            await call("Input.dispatchKeyEvent", {
                "type": "keyDown", "modifiers": 2, "key": "+",
                "code": "Equal", "windowsVirtualKeyCode": 187,
            }, sess)
            await call("Input.dispatchKeyEvent", {
                "type": "keyUp", "modifiers": 2, "key": "+",
                "code": "Equal", "windowsVirtualKeyCode": 187,
            }, sess)
        print("窗口已最大化，页面缩放已放大两档（约 125%）")


if __name__ == "__main__":
    warm()
    asyncio.run(window_setup())
    print("预热完成，可以开始录制流程。")
