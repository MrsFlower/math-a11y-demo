# -*- coding: utf-8 -*-
"""第三轮：跑真实 content.js 提取、看代码块/段落内容、模拟选区文本。"""
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

EXPR = r"""(function(){
  var out = {};
  // 代码块里是否有 LaTeX（单反斜杠命令）
  var codes = document.querySelectorAll('pre, code');
  out.code_blocks = codes.length;
  out.code_latex = [];
  for (var c = 0; c < codes.length; c++) {
    var t = (codes[c].textContent || '').trim();
    if (/\\(frac|sum|int|sqrt|alpha|beta|infty|mathbb|begin|cdot|times|lim|partial)/.test(t)) {
      out.code_latex.push(t.slice(0, 90));
      if (out.code_latex.length >= 6) break;
    }
  }
  // 正文段落里带 $ 定界符的（未渲染的原始 LaTeX）
  var paras = document.querySelectorAll('p, li');
  out.dollar_paras = [];
  for (var p = 0; p < paras.length; p++) {
    var pt = (paras[p].textContent || '');
    if (/\$[^$]+\$/.test(pt) || /\\(frac|sum|int|sqrt)/.test(pt)) {
      out.dollar_paras.push(pt.trim().slice(0, 120));
      if (out.dollar_paras.length >= 6) break;
    }
  }
  // 模拟选区：选第一个 code_latex 所在块或第一个含公式段落
  var target = null;
  for (var c2 = 0; c2 < codes.length; c2++) {
    var t2 = (codes[c2].textContent || '').trim();
    if (/\\(frac|sum|int|sqrt|alpha|beta|infty|mathbb|begin|cdot|times|lim|partial)/.test(t2)) { target = codes[c2]; break; }
  }
  if (!target) {
    for (var p2 = 0; p2 < paras.length; p2++) {
      if (/\$[^$]+\$/.test(paras[p2].textContent || '')) { target = paras[p2]; break; }
    }
  }
  if (target) {
    var sel = window.getSelection();
    var saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
    sel.removeAllRanges();
    var rng = document.createRange();
    rng.selectNodeContents(target);
    sel.addRange(rng);
    out.selection_sample = sel.toString().slice(0, 200);
    sel.removeAllRanges();
    if (saved) sel.addRange(saved); // 恢复原选区，不留脏状态
  } else {
    out.selection_sample = '(无公式目标可选)';
  }
  // 是否有登录墙
  var bt = (document.body.innerText || '');
  out.login_wall = /打开 App|登录查看|扫码登录|登录后查看/.test(bt);
  return JSON.stringify(out, null, 1);
})()"""


async def main():
    ws = json.load(urllib.request.urlopen("http://127.0.0.1:9333/json/version"))["webSocketDebuggerUrl"]
    async with websockets.connect(ws, origin=None, max_size=10 * 1024 * 1024) as w:
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
        targets = r["result"]["targetInfos"]
        for url in ["zhuanlan.zhihu.com/p/589099791", "cloud.tencent.com/developer/article/2123736"]:
            t = next((x for x in targets if url in x.get("url", "") and x["type"] == "page"), None)
            print("===", url, "===")
            if not t:
                print("!! 标签没找到")
                continue
            r = await call("Target.attachToTarget", {"targetId": t["targetId"], "flatten": True})
            sess = r["result"]["sessionId"]
            r = await call("Runtime.evaluate", {"expression": EXPR, "returnByValue": True}, sess)
            print(r["result"]["result"].get("value"))
            # 跑真实的 content.js
            r = await call("Runtime.evaluate", {"expression": CONTENT_JS, "returnByValue": True}, sess)
            found = r["result"]["result"].get("value")
            print("content.js 提取结果:", json.dumps(found, ensure_ascii=False)[:600] if found else found)


asyncio.run(main())
