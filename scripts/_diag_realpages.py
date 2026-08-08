# -*- coding: utf-8 -*-
"""诊断目标页面的公式渲染方式：统计各种公式 DOM 的数量并采样。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

URLS = [
    "https://zhuanlan.zhihu.com/p/589099791",
    "https://cloud.tencent.com/developer/article/2123736",
]

EXPR = r"""(function(){
  var out = {};
  out.title = document.title;
  out.annotation = document.querySelectorAll('annotation[encoding="application/x-tex"]').length;
  out.mjx_script = document.querySelectorAll('script[type^="math/tex"]').length;
  out.math_tag = document.querySelectorAll('math').length;
  out.mjx_container = document.querySelectorAll('mjx-container').length;
  out.katex = document.querySelectorAll('.katex').length;
  out.eeimg = document.querySelectorAll('img[eeimg]').length;
  out.mwe_math = document.querySelectorAll('img.mwe-math-fallback-image-inline,img.mwe-math-fallback-image-display').length;
  var imgs = document.querySelectorAll('img[eeimg]');
  out.eeimg_sample = [];
  for (var i = 0; i < Math.min(3, imgs.length); i++) {
    out.eeimg_sample.push({ alt: (imgs[i].alt || '').slice(0, 120), src: (imgs[i].src || '').slice(0, 80) });
  }
  // MathJax v3 mjx-container 采样：看 assistive mml / alttext
  var mjx = document.querySelectorAll('mjx-container');
  out.mjx_sample = [];
  for (var j = 0; j < Math.min(2, mjx.length); j++) {
    var c = mjx[j];
    var ann = c.querySelector('annotation[encoding="application/x-tex"]');
    out.mjx_sample.push({
      aria: (c.getAttribute('aria-label') || '').slice(0, 80),
      has_annotation: !!ann,
      ann_text: ann ? ann.textContent.slice(0, 80) : '',
      inner_len: c.textContent.length
    });
  }
  // katex 采样
  var kt = document.querySelectorAll('.katex');
  out.katex_sample = [];
  for (var k = 0; k < Math.min(2, kt.length); k++) {
    var ann2 = kt[k].querySelector('annotation[encoding="application/x-tex"]');
    out.katex_sample.push({ has_annotation: !!ann2, ann_text: ann2 ? ann2.textContent.slice(0, 80) : '' });
  }
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

        for url in URLS:
            r = await call("Target.createTarget", {"url": url})
            tid = r["result"]["targetId"]
            await asyncio.sleep(10)
            r = await call("Target.attachToTarget", {"targetId": tid, "flatten": True})
            sess = r["result"]["sessionId"]
            r = await call("Runtime.evaluate", {"expression": EXPR, "returnByValue": True}, sess)
            print("===", url, "===")
            print(r["result"]["result"].get("value"))


asyncio.run(main())
