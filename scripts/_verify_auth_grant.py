# -*- coding: utf-8 -*-
"""验证 v0.8.1 自愈授权流程（CDP 无法点原生授权对话框，
用 userGesture=true 的 Runtime.evaluate 等效模拟用户按按钮触发的授权请求）。"""
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
  const out = { steps: [] };
  const wait = (ms) => new Promise(r => setTimeout(r, ms));
  const status = () => document.getElementById("status").textContent;
  out.version = chrome.runtime.getManifest().version;

  // 1) 打开普通页（无 activeTab 授权）
  await chrome.tabs.create({ url: "https://example.com", active: true });
  await wait(2000);

  // 2) 触发提取 → 应失败并出现授权按钮（焦点落按钮）
  extractPage();
  await wait(1500);
  const btn = document.getElementById("auth-grant-btn");
  out.steps.push({
    step: "提取失败后",
    btnVisible: !btn.hidden,
    btnFocused: document.activeElement === btn,
    status: status(),
  });
  if (btn.hidden) return JSON.stringify(out);

  // 3) 模拟用户按「授权并重试」按钮（userGesture 由 CDP evaluate 注入）
  btn.click();
  for (let i = 0; i < 20; i++) {
    await wait(500);
    if (/授权成功|未获得授权|授权请求失败/.test(status())) break;
  }
  out.steps.push({ step: "点击授权按钮后", status: status() });

  // 4) 若自动重试成功，候选/提示区应有反应；再确认权限已持久
  await wait(2000);
  out.steps.push({ step: "重试完成后", status: status() });
  out.allUrlsGranted = await chrome.permissions.contains({ origins: ["<all_urls>"] });
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
                print(f"版本：{data['version']}")
                for s in data["steps"]:
                    print(json.dumps(s, ensure_ascii=False, indent=1))
                print("all_urls 权限已持有:", data.get("allUrlsGranted"))
                return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
