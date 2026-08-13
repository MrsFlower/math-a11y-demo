# -*- coding: utf-8 -*-
"""在复现页上注入现有 content.js，核对各候选的 extractor 归属，验证偏差根因。"""
import asyncio
import json
import pathlib
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CDP = "http://127.0.0.1:9333"
EXT_ID = "nnhjbbjogdfgnipomcmogkoimopnkbaj"
CONTENT_JS = pathlib.Path(r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\extension\content.js").read_text(encoding="utf-8")
PROBE_URL = "http://127.0.0.1:8399/gaokao_probe.html"


def targets():
    return json.loads(urllib.request.urlopen(f"{CDP}/json/list", timeout=5).read())


async def main() -> int:
    ctx = None
    for t in targets():
        if t["url"] == f"chrome-extension://{EXT_ID}/sidepanel.html" and t["type"] == "page":
            ctx = t
    if not ctx:
        req = urllib.request.Request(f"{CDP}/json/new?chrome-extension://{EXT_ID}/sidepanel.html", method="PUT")
        urllib.request.urlopen(req, timeout=5)
        await asyncio.sleep(3)
        for t in targets():
            if t["url"] == f"chrome-extension://{EXT_ID}/sidepanel.html" and t["type"] == "page":
                ctx = t
    if not ctx:
        print("无 sidepanel 上下文")
        return 1

    js = (r"""
(async () => {
  const out = { cases: [] };
  let tab = await chrome.tabs.create({ url: "__URL__", active: true });
  await new Promise(r => setTimeout(r, 4000));
  tab = await chrome.tabs.get(tab.id);
  out.tabUrl = tab.url || "(未知)";
  try {
    const [res] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    const found = (res && res.result) || [];
    out.count = found.length;
    for (const f of found) {
      out.cases.push({
        latex: f.latex.slice(0, 90),
        kind: f.kind,
        extractor: f.debug.extractor,
        conf: f.confidence,
        ctxHead: (f.context || "").slice(0, 40),
      });
    }
  } catch (e) {
    out.error = String(e && e.message);
  }
  try { await chrome.tabs.remove(tab.id); } catch (_) {}
  return JSON.stringify(out);
})()
""").replace("__URL__", PROBE_URL)

    async with websockets.connect(ctx["webSocketDebuggerUrl"], max_size=10 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": js, "awaitPromise": True, "returnByValue": True}}))
        while True:
            d = json.loads(await ws.recv())
            if d.get("id") == 1:
                v = d.get("result", {}).get("result", {}).get("value")
                if not v:
                    print("执行失败:", json.dumps(d, ensure_ascii=False)[:600])
                    return 1
                data = json.loads(v)
                if data.get("error"):
                    print("注入失败:", data["error"])
                    return 1
                print(f"tab.url={data['tabUrl']}  共 {data['count']} 条\n")
                for i, c in enumerate(data["cases"], 1):
                    print(f"{i:2d}. [{c['extractor']}|{c['kind']}|{c['conf']}] {c['latex']}")
                return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
