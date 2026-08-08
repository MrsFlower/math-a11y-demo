# -*- coding: utf-8 -*-
"""第二轮诊断：细看两页公式的真实 DOM（MathJax 容器、图片、代码块、选区文本）。"""
import asyncio
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import websockets

EXPR = r"""(function(){
  var out = {};
  out.body_len = (document.body.innerText || '').length;
  // MathJax v2 渲染容器
  var mj = document.querySelectorAll('span.MathJax');
  out.mathjax_v2_rendered = mj.length;
  out.mj_sample = [];
  for (var i = 0; i < Math.min(3, mj.length); i++) {
    var m = mj[i];
    var parent = m.closest('div, p, li');
    out.mj_sample.push({
      text_len: m.textContent.length,
      text_sample: m.textContent.slice(0, 60),
      aria: (m.getAttribute('aria-label') || m.getAttribute('aria-hidden') || ''),
      has_assistive: !!m.querySelector('.MJX_Assistive_MathML, math')
    });
  }
  // math/tex 脚本内容采样
  var sc = document.querySelectorAll('script[type^="math/tex"]');
  out.tex_scripts = [];
  for (var s = 0; s < Math.min(5, sc.length); s++) {
    out.tex_scripts.push({
      type: sc[s].type,
      text: sc[s].textContent.slice(0, 100),
      rendered: !!(sc[s].nextElementSibling && sc[s].nextElementSibling.className && String(sc[s].nextElementSibling.className).indexOf('MathJax') >= 0)
    });
  }
  // 图片里有没有公式图（svg/png，src 含 tex/latex/equation/formula/math/svg）
  var imgs = document.querySelectorAll('img');
  out.img_total = imgs.length;
  out.img_formula_like = [];
  for (var k = 0; k < imgs.length; k++) {
    var src = imgs[k].src || '';
    if (/tex|latex|equation|formula|math|svg|codecogs/i.test(src)) {
      out.img_formula_like.push({ src: src.slice(0, 120), alt: (imgs[k].alt || '').slice(0, 80), cls: imgs[k].className });
      if (out.img_formula_like.length >= 5) break;
    }
  }
  // svg 数量（MathJax v3 SVG 输出 / 站点自渲染）
  out.svg_total = document.querySelectorAll('svg').length;
  // 代码块采样（教程类文章公式常以代码形式出现）
  var codes = document.querySelectorAll('pre, code');
  out.code_blocks = codes.length;
  out.code_sample = [];
  for (var c = 0; c < Math.min(3, codes.length); c++) {
    var t = (codes[c].textContent || '').trim();
    if (/\\\\|frac|sum|int|sqrt|alpha|beta/.test(t)) out.code_sample.push(t.slice(0, 100));
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


asyncio.run(main())
