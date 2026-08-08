# -*- coding: utf-8 -*-
"""验证：在测试浏览器里打开插件自带测试页，跑真实 content.js，统计提取条数。"""
import asyncio
import json
import pathlib
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

CONTENT_JS = pathlib.Path(
    r"c:\Users\15866\Documents\codeheaven\小程序大赛\math-a11y-assistant\extension\content.js"
).read_text(encoding="utf-8")

PAGE_URL = "http://127.0.0.1:8321/static/plugin_test_page.html"
CDP = "http://127.0.0.1:9333"


def http_json(method: str, url: str):
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


async def main() -> int:
    # 新建一个标签页打开测试页（新版 CDP 要求 PUT，旧版 GET，两种都试）
    try:
        target = http_json("PUT", f"{CDP}/json/new?{PAGE_URL}")
    except Exception:
        target = http_json("GET", f"{CDP}/json/new?{PAGE_URL}")
    ws_url = target["webSocketDebuggerUrl"]
    tab_id = target["id"]

    msg_id = 0

    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        async def send(method: str, params: dict | None = None) -> dict:
            nonlocal msg_id
            msg_id += 1
            await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
            while True:
                d = json.loads(await ws.recv())
                if d.get("id") == msg_id:
                    return d

        await asyncio.sleep(1.5)  # 等页面加载
        expr = CONTENT_JS
        r = await send("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
        })
        formulas = (r.get("result", {}).get("result", {}) or {}).get("value")
        if formulas is None:
            print("提取失败:", json.dumps(r, ensure_ascii=False)[:500])
            return 1

        print(f"共提取 {len(formulas)} 条：")
        by_source = {}
        for i, f in enumerate(formulas, 1):
            by_source.setdefault(f["source"], []).append(i)
            debug = f.get("debug") or {}
            confidence = f.get("confidence", "?")
            extractor = debug.get("extractor", "?")
            print(f"  {i:>2}. [{f['kind']}/{confidence}/{extractor}] ({f['source']}) {f['latex'][:70]}")
        print("\n按来源统计：")
        for src, ids in by_source.items():
            print(f"  {src}: {len(ids)} 条 {ids}")
        ok = len(formulas) == 10
        print("\n结论：", "通过（10 条）" if ok else f"不通过（{len(formulas)} 条，预期 10 条）")
        # 关闭测试标签页
        try:
            http_json("GET", f"{CDP}/json/close/{tab_id}")
        except Exception:
            pass
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
