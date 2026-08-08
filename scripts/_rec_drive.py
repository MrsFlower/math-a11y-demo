# -*- coding: utf-8 -*-
"""录制驱动：用户按 Ctrl+Shift+M 打开侧边栏后运行，自动完成镜头 2~4。

流程：等转译完成 → 点「转去理解模式」→ 等讲解完成 → 听 AI 讲解（TTS）
→ 追问一问 → 完成提示。每步之间有停顿，给 NVDA 朗读留时间。
"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

PAUSE = 2.5  # 每步之间的朗读停顿（秒）


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

        # 1. 等侧边栏 target 出现（用户按快捷键后）
        # 注意：部分 Chrome 版本里侧边栏 target 的 type 是 page 而非 side_panel
        panel_tid = None
        print("[..] 等待侧边栏打开（按 Ctrl+Shift+M）…", flush=True)
        for i in range(120):
            r = await call("Target.getTargets")
            for t in r["result"]["targetInfos"]:
                if "sidepanel.html" in t.get("url", ""):
                    panel_tid = t["targetId"]
            if panel_tid:
                break
            if i and i % 10 == 0:
                print(f"[..] 已等待 {i} 秒，仍未出现侧边栏…", flush=True)
            await asyncio.sleep(1)
        if not panel_tid:
            print("!! 2 分钟内没等到侧边栏。请确认已按 Ctrl+Shift+M，然后重跑本脚本。")
            return
        print("[OK] 侧边栏已打开")
        r = await call("Target.attachToTarget", {"targetId": panel_tid, "flatten": True})
        sess = r["result"]["sessionId"]

        async def ev(expr):
            r = await call("Runtime.evaluate",
                           {"expression": expr, "returnByValue": True, "awaitPromise": True}, sess)
            return r["result"]["result"].get("value")

        async def wait_until(check_expr, desc, timeout=90):
            for _ in range(timeout * 2):
                v = await ev(check_expr)
                if v:
                    print(f"[OK] {desc}")
                    return True
                await asyncio.sleep(0.5)
            print(f"!! 等待超时：{desc}")
            return False

        # 2. 等转译完成
        await wait_until(
            "document.getElementById('transcribe-slot') && "
            "document.getElementById('transcribe-slot').textContent.trim().length>0",
            "转译结果已出现", timeout=45)
        await asyncio.sleep(PAUSE + 2)

        # 3. 转去理解模式（镜头 3 开始）
        await ev("var b=document.getElementById('transcribe-to-explain-btn'); b.focus(); b.click(); 'clicked'")
        print("[..] 已点击「转去理解模式」，等待确认框出现…")
        ok = await wait_until(
            "document.getElementById('confirm-box') && "
            "!document.getElementById('confirm-box').hidden",
            "确认框已出现", timeout=15)
        if ok:
            await asyncio.sleep(PAUSE)
            await ev("var b=document.getElementById('confirm-btn'); b.focus(); b.click(); 'confirmed'")
            print("[..] 已点击「确认并分析」，等待 AI 讲解（约 20 秒）…")
        else:
            print("[..] 未出现确认框，直接等待讲解（可能已跳过确认步）")
        await wait_until(
            "document.getElementById('result-section') && "
            "!document.getElementById('result-section').hidden",
            "讲解结果已显示", timeout=90)
        await asyncio.sleep(PAUSE + 3)

        # 4. 听 AI 讲解（TTS 播 8 秒再停）
        await ev("var b=document.getElementById('ai-speak-btn'); b.focus(); b.click(); 'clicked'")
        print("[..] TTS 播放中（8 秒）…")
        await asyncio.sleep(8)
        await ev("var b=document.getElementById('ai-speak-btn'); b.click(); 'stopped'")
        print("[OK] TTS 已停止")
        await asyncio.sleep(PAUSE)

        # 5. 追问（镜头 4）
        await ev(
            "var i=document.getElementById('ask-input');"
            "i.focus(); i.value='这个公式在物理里有什么应用？';"
            "i.dispatchEvent(new Event('input',{bubbles:true})); 'typed'")
        await asyncio.sleep(1)
        await ev("var b=document.getElementById('ask-btn'); b.focus(); b.click(); 'asked'")
        print("[..] 追问已发送，等待回答…")
        await wait_until(
            "document.getElementById('answer-slot') && "
            "!document.getElementById('answer-slot').hidden && "
            "document.getElementById('answer-slot').textContent.trim().length>0",
            "追问回答已出现", timeout=60)
        await asyncio.sleep(PAUSE + 3)

        print("\n=== 镜头 2~4 全部完成 ===")
        print("接下来：Alt+Tab 切到收尾介绍页（浏览器里已打开 dist/rec_endcard.html），")
        print("停留 5 秒后停止 Win+G 录制。")


asyncio.run(main())
