# -*- coding: utf-8 -*-
"""验证 v0.8.3：忙碌状态反馈（焦点落状态区、文案进行中语义）+ 紧凑分式读法全链路。
前置：本机服务已起在 127.0.0.1:8321（脚本会把侧边栏指向它）。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
EXT_ID = "nnhjbbjogdfgnipomcmogkoimopnkbaj"

JS = r"""
(async () => {
  const out = {};
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const statusEl = () => document.getElementById("status");
  out.version = chrome.runtime.getManifest().version;
  out.radios = document.querySelectorAll('input[name="fraction-style"]').length;
  out.hasBusyFn = typeof enterBusyState === "function";

  // 指向本机服务 + 紧凑分式读法
  localStorage.setItem("math_a11y_api_base_v1", "http://127.0.0.1:8321");
  localStorage.setItem("math_a11y_fraction_style_v1", "compact");
  document.querySelectorAll('input[name="fraction-style"]').forEach(r => r.checked = r.value === "compact");

  // 触发讲解：走真实用户路径——确认框填公式并点「确认并讲解」。
  // 点击让页面与按钮获得焦点（CDP 直调函数时页面无焦点，focus() 不生效，
  // 无法复现真实交互），随后同步段应立即进入忙碌态（焦点落状态区）
  document.getElementById("confirm-input").value = "\\frac{1}{2}";
  document.getElementById("confirm-btn").click();
  await wait(400);
  out.busy = {
    focusOnStatus: document.activeElement === statusEl(),
    status: statusEl().textContent.slice(0, 80),
  };

  // 等讲解完成（本地大模型最多 90 秒）
  for (let i = 0; i < 60; i++) {
    await wait(1500);
    const s = statusEl().textContent;
    if (/讲解完成|讲解失败|无法连接/.test(s)) { out.finalStatus = s.slice(0, 120); break; }
  }
  out.speech = (typeof currentData !== "undefined" && currentData && currentData.speech_text) || null;

  // AI 语音按钮忙碌态：文案换「生成音频中」，焦点落状态区
  if (currentData) {
    const btn = document.getElementById("ai-speak-btn");
    btn.click();
    await wait(600);
    out.aiBusy = {
      btnText: btn.textContent,
      focusOnStatus: document.activeElement === statusEl(),
      status: statusEl().textContent.slice(0, 60),
    };
    await wait(1500);
    stopAiSpeak();
    out.aiRestored = btn.textContent;
  }
  // 恢复默认云端，避免影响后续人工测试
  localStorage.removeItem("math_a11y_api_base_v1");
  return JSON.stringify(out);
})()
"""


async def main() -> int:
    ctx = None
    for _try in range(3):
        targets = json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=5).read())
        for t in targets:
            if t["url"] == f"chrome-extension://{EXT_ID}/sidepanel.html" and t["type"] == "page":
                ctx = t
        if ctx:
            break
        req = urllib.request.Request(f"{CDP}/json/new?chrome-extension://{EXT_ID}/sidepanel.html", method="PUT")
        urllib.request.urlopen(req, timeout=5)
        await asyncio.sleep(2)
    if not ctx:
        print("找不到 sidepanel 页上下文")
        return 1
    await asyncio.sleep(3)
    async with websockets.connect(ctx["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": JS, "awaitPromise": True,
                                             "returnByValue": True, "userGesture": True}}))
        while True:
            d = json.loads(await ws.recv())
            if d.get("id") == 1:
                v = d.get("result", {}).get("result", {}).get("value")
                if not v:
                    print("执行失败:", json.dumps(d, ensure_ascii=False)[:800])
                    return 1
                data = json.loads(v)
                print(json.dumps(data, ensure_ascii=False, indent=1))
                ok = (
                    data.get("version") == "0.8.3"
                    and data.get("radios") == 2
                    and data.get("hasBusyFn")
                    and data.get("busy", {}).get("focusOnStatus")
                    and data.get("speech") == "2 分之 1"
                    and data.get("aiBusy", {}).get("btnText") == "生成音频中"
                    and data.get("aiBusy", {}).get("focusOnStatus")
                    and data.get("aiRestored") == "听 AI 讲解"
                )
                print("总体判定:", "通过" if ok else "未通过")
                return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
