# -*- coding: utf-8 -*-
"""复现「此页面无法提取」：在测试浏览器 SW 上下文跑真实 chrome.scripting.executeScript，
逐一记录各类页面的成功/失败与真实错误消息，为侧边栏诊断功能定稿提供依据。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"

# 覆盖真实用户可能遇到的页面类型
SCENARIOS = [
    ("普通网页（对照）", "https://example.com"),
    ("浏览器内置页 edge://extensions", "edge://extensions"),
    ("浏览器内置页 edge://settings", "edge://settings"),
    ("新标签页 edge://newtab", "edge://newtab"),
    ("data: URL", "data:text/html,<p>hello</p>"),
    ("本地文件 file://", "file:///C:/Users/15866/Documents/codeheaven/小程序大赛/_cdp_profile/file_probe.html"),
]

JS = r"""
(async () => {
  const out = { name: chrome.runtime.getManifest().name, version: chrome.runtime.getManifest().version, cases: [] };
  const scenarios = __SCENARIOS__;
  for (const [label, url] of scenarios) {
    let tab;
    try {
      tab = await chrome.tabs.create({ url, active: true });
    } catch (e) {
      out.cases.push({ label, url, createError: String(e && e.message) });
      continue;
    }
    await new Promise(r => setTimeout(r, 1500));
    try { tab = await chrome.tabs.get(tab.id); } catch (_) {}
    const entry = { label, url, tabUrl: tab.url || "(未知)" };
    try {
      const res = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      const found = (res && res[0] && res[0].result) || [];
      entry.ok = true;
      entry.formulaCount = found.length;
    } catch (e) {
      entry.ok = false;
      entry.error = String(e && e.message);
    }
    out.cases.push(entry);
    try { await chrome.tabs.remove(tab.id); } catch (_) {}
  }
  return JSON.stringify(out);
})()
"""


_probe_id = 0


async def probe_sw(ws_url: str, expr: str):
    global _probe_id
    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        _probe_id += 1
        mid = _probe_id
        await ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "awaitPromise": True, "returnByValue": True}}))
        while True:
            d = json.loads(await ws.recv())
            if d.get("id") == mid:
                return d.get("result", {}).get("result", {}).get("value")


def http_json(method: str, url: str):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


async def main() -> int:
    # MV3 SW 会休眠且不一定出现在列表：优先用 SW，否则打开 sidepanel 页用扩展页上下文
    # （两种上下文的 chrome.scripting.executeScript 行为一致）
    EXT_ID = "nnhjbbjogdfgnipomcmogkoimopnkbaj"
    ctx = None
    for _wake in range(3):
        targets = http_json("GET", f"{CDP}/json/list")
        for t in targets:
            if t["url"] == f"chrome-extension://{EXT_ID}/sidepanel.html" and t["type"] == "page":
                ctx = t
                break
        if ctx:
            break
        try:
            http_json("PUT", f"{CDP}/json/new?chrome-extension://{EXT_ID}/sidepanel.html")
        except Exception:
            pass
        await asyncio.sleep(2)
    if not ctx:
        print("找不到插件执行上下文（sidepanel 页）")
        return 1
    await asyncio.sleep(2)  # 等 sidepanel 初始化完
    msg_id = 0
    async with websockets.connect(ctx["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        async def send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                d = json.loads(await ws.recv())
                if d.get("id") == msg_id:
                    return d

        expr = JS.replace("__SCENARIOS__", json.dumps(SCENARIOS, ensure_ascii=False))
        r = await send("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True})
        val = r.get("result", {}).get("result", {}).get("value")
        if not val:
            print("执行失败:", json.dumps(r, ensure_ascii=False)[:800])
            return 1
        data = json.loads(val)
        print(f"扩展：{data['name']} v{data['version']}\n")
        for c in data["cases"]:
            if c.get("createError"):
                print(f"[建页失败] {c['label']}: {c['createError']}")
            elif c["ok"]:
                print(f"[可注入  ] {c['label']}（提取 {c.get('formulaCount')} 条）")
            else:
                print(f"[无法注入] {c['label']}\n           tab.url={c.get('tabUrl')}\n           真实错误：{c.get('error')}")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
