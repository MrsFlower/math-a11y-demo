// 页面公式提取脚本：由面板通过 chrome.scripting.executeScript 按需注入，
// 不常驻页面（避免干扰读屏）。整个文件是一个 IIFE，返回值即注入结果。
//
// 捕获优先级（能拿到源码就绝不识别）：
//   1. KaTeX / MathJax v3 的 <annotation encoding="application/x-tex">  → 原始 LaTeX，零误差
//   2. MathJax v2 的 <script type="math/tex">                           → 原始 LaTeX
//   3. 维基百科公式图 img.mwe-math-fallback-image-* 的 alt              → 原始 LaTeX
//   4. <math> 的 alttext 属性                                           → 通常是 LaTeX
//   5. 裸 <math> 的文本内容                                             → 需走 normalize 转换确认
//
// 返回：[{ latex, source, kind, context }]，kind = "latex"（直接确认）| "text"（先转换）
// context = 公式周围的正文文字（供后端消歧义：页面上公式旁边往往写着它叫什么）
(() => {
  const found = [];
  const seen = new Set();
  const MAX = 30;

  // 往上找最近的、有足够正文的祖先（段落级），截取其文字作为上下文。
  // 两个坑：①KaTeX/MathJax 把 annotation 埋在多层壳里，要爬 8 层才能越过渲染容器；
  // ②长公式自身文本就超 30 字，semantics 这类壳会被误认为「有正文」。
  // 所以判据是：祖先文本刨去公式自身后还剩 >=30 字才算真正文（注意 annotation/script
  // 常被 display:none，祖先的 innerText 可能本来就不含公式文本，两种情况都要处理）。
  function contextOf(el) {
    const own = (el.textContent || "").replace(/\s+/g, " ").trim();
    let node = el;
    for (let i = 0; i < 8 && node && node.parentElement; i++) {
      node = node.parentElement;
      if (node.tagName === "BODY" || node.tagName === "HTML") break;
      const t = (node.innerText || node.textContent || "").replace(/\s+/g, " ").trim();
      const extra = own && t.includes(own) ? t.length - own.length : t.length;
      if (extra >= 30) return t.slice(0, 400);
    }
    return "";
  }

  function push(raw, source, kind, el) {
    if (found.length >= MAX) return;
    const t = (raw || "").replace(/^\s*\\displaystyle\s*/, "").trim();
    if (!t || t.length > 2000 || seen.has(t)) return;
    seen.add(t);
    found.push({ latex: t, source, kind, context: el ? contextOf(el) : "" });
  }

  // 1. KaTeX / MathJax v3 annotation（页面自带 LaTeX 源码）
  document
    .querySelectorAll('annotation[encoding="application/x-tex"]')
    .forEach((a) => push(a.textContent, "页面自带 LaTeX 源码", "latex", a));

  // 2. MathJax v2：<script type="math/tex"> / "math/tex; mode=display"
  document
    .querySelectorAll('script[type^="math/tex"]')
    .forEach((s) => push(s.textContent, "页面自带 LaTeX 源码（MathJax）", "latex", s));

  // 3. 维基百科公式图：alt 属性就是 LaTeX
  document
    .querySelectorAll(
      "img.mwe-math-fallback-image-inline, img.mwe-math-fallback-image-display"
    )
    .forEach((img) => push(img.alt, "维基百科公式图替代文本", "latex", img));

  // 4/5. 其余 <math> 节点：优先 alttext，否则退回文本内容（需转换）
  document.querySelectorAll("math").forEach((m) => {
    if (m.querySelector('annotation[encoding="application/x-tex"]')) return; // 已在第 1 步捕获
    const alt = m.getAttribute("alttext");
    if (alt) {
      push(alt, "MathML alttext 属性", "latex", m);
    } else {
      push(m.textContent, "MathML 文本（无源码，需转换确认）", "text", m);
    }
  });

  return found;
})();
