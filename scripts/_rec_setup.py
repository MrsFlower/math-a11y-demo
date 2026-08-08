# -*- coding: utf-8 -*-
"""录制预置：开录前跑一次。
1. 预置快捷键默认行为（selection_transcribe），避免首次设置页打断录制；
2. 生成镜头 5 收尾介绍页（dist/rec_endcard.html）；
3. 在练习页选中含公式的段落并把光标就位。
"""
import asyncio
import json
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import websockets

ROOT = Path(__file__).resolve().parent.parent

ENDCARD = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>数学公式无障碍学习助手</title>
<style>
body { font-family:"Microsoft YaHei",sans-serif; background:#0f2a52; color:#fff;
  display:flex; flex-direction:column; justify-content:center; align-items:center;
  height:100vh; margin:0; text-align:center; }
h1 { font-size:44px; margin:0 0 18px; }
p.slogan { font-size:26px; color:#cfe0ff; margin:0 0 40px; }
ul { list-style:none; padding:0; font-size:20px; line-height:2.1; color:#e8efff; }
li::before { content:"✓ "; color:#7fd18f; font-weight:bold; }
</style></head><body>
<h1>数学公式无障碍学习助手</h1>
<p class="slogan">让每个公式都读得出来、学得明白</p>
<ul>
<li>浏览器插件 · 全程键盘操作 · 读屏友好</li>
<li>公式转译：本地规则秒转 + 大模型兜底</li>
<li>AI 讲解：五段式结构稿 · 语音合成 · 可追问</li>
<li>云端部署开箱即用 · 代码开源</li>
</ul>
</body></html>
"""


async def main():
    (ROOT / "dist" / "rec_endcard.html").write_text(ENDCARD, encoding="utf-8")
    print("收尾介绍页已生成: dist/rec_endcard.html")

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

        # 1. 预置快捷键偏好（先唤醒 service worker 再设置）
        # 注意：不要在这里 Extensions.loadUnpacked——反复重装会把扩展状态搞坏，
        # 导致 SW 拉不起来、快捷键失灵。SW 休眠时直接开 background.js 页面唤醒即可。
        r = await call("Target.getTargets")
        ext_id = None
        for t in r["result"]["targetInfos"]:
            u = t.get("url", "")
            if u.startswith("chrome-extension://") and (
                    "sidepanel.html" in u or t["type"] == "service_worker"
                    or "background.js" in u):
                ext_id = u.split("//")[1].split("/")[0]
                break
        if not ext_id:
            print("!! 找不到扩展。请先在测试浏览器加载 extension 目录，再重跑本脚本。")
            return
        dummy = await call("Target.createTarget",
                           {"url": f"chrome-extension://{ext_id}/background.js"})
        sw = None
        for _ in range(6):
            await asyncio.sleep(1)
            r = await call("Target.getTargets")
            sw = next((t for t in r["result"]["targetInfos"]
                       if t["type"] == "service_worker" and ext_id in t.get("url", "")), None)
            if sw:
                break
        await call("Target.closeTarget", {"targetId": dummy["result"]["targetId"]})
        if sw:
            r = await call("Target.attachToTarget", {"targetId": sw["targetId"], "flatten": True})
            sess = r["result"]["sessionId"]
            expr = ("chrome.storage.local.set({math_a11y_shortcut_prefs_v1:"
                    "{setupDone:true,shortcutMode:'selection_transcribe',"
                    "transcribeProfile:'spoken_structured'}}).then(()=>'prefs-set')")
            r = await call("Runtime.evaluate", {"expression": expr, "awaitPromise": True,
                                                "returnByValue": True}, sess)
            print("快捷键偏好预置:", r["result"]["result"].get("value"))
        else:
            print("!! SW 唤醒失败：扩展状态可能已损坏。请到 chrome://extensions 手动移除")
            print("   本扩展后重新「加载已解压的扩展」，再重跑本脚本。")
            return

        # 2. 练习页：选中含积分公式的段落
        r = await call("Target.getTargets")
        tab = next((t for t in r["result"]["targetInfos"]
                    if t["type"] == "page" and "plugin_test_page" in t.get("url", "")), None)
        if not tab:
            print("警告: 练习页未打开")
            return
        r = await call("Target.activateTarget", {"targetId": tab["targetId"]})
        r = await call("Target.attachToTarget", {"targetId": tab["targetId"], "flatten": True})
        sess = r["result"]["sessionId"]
        expr = (
            "(function(){"
            "var ps=document.querySelectorAll('p');"
            "var target=null;"
            "for(var i=0;i<ps.length;i++){if(ps[i].textContent.indexOf('\\u222b')>=0){target=ps[i];break;}}"
            "if(!target&&ps.length){target=ps[0];}"
            "if(!target)return 'no-paragraph';"
            "var rng=document.createRange();rng.selectNodeContents(target);"
            "var sel=window.getSelection();sel.removeAllRanges();sel.addRange(rng);"
            "target.tabIndex=-1;target.focus();"
            "return 'selected: '+target.textContent.slice(0,30);"
            "})()"
        )
        r = await call("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sess)
        print("选区预置:", r["result"]["result"].get("value"))
        await call("Target.detachFromTarget", {"sessionId": sess})
    print("预置完成。接下来按录制口令操作。")


asyncio.run(main())
