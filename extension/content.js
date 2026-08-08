// 页面公式提取脚本：由面板通过 chrome.scripting.executeScript 按需注入，
// 不常驻页面（避免干扰读屏）。整个文件是一个 IIFE，返回值即注入结果。
//
// 捕获优先级（能拿到源码就绝不识别）：
//   1. KaTeX / MathJax v3 的 <annotation encoding="application/x-tex">  → 原始 LaTeX，零误差
//   2. MathJax v2 的 <script type="math/tex">                           → 原始 LaTeX
//   3. 维基百科公式图 img.mwe-math-fallback-image-* 的 alt              → 原始 LaTeX
//   4. <math> 的 alttext 属性                                           → 通常是 LaTeX
//   5. 裸 <math> 的文本内容                                             → 需走 normalize 转换确认
//   6. 代码块里的 LaTeX 源码（教程类文章：公式不渲染，就写在代码块里） → 原始 LaTeX
//   7. 正文里的纯文本公式（视觉公式/ASCII 记号/化学式嵌在文字中）   → 需走 normalize 转译
//
// 返回：[{ latex, source, kind, context }]，kind = "latex"（直接确认）| "text"（先转换）
// context = 公式周围的正文文字（供后端消歧义：页面上公式旁边往往写着它叫什么）
(() => {
  const found = [];
  const seen = new Set();
  // 上限取 60：实测 AI Studio 粘贴的高等数学期末试卷一页就有 51 个公式，
  // 30 会截断掉半张卷子；再高会让侧边栏列表过长、逐条转译变慢。
  const MAX = 60;

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
      // 克隆后再取文本：KaTeX 的隐藏 MathML 读屏层会逐字泄进 innerText
      // （「𝑥 → 0 x→0」双层重复乱码），连同 annotation/script 源码标签一起剔除
      const clone = node.cloneNode(true);
      clone.querySelectorAll(".katex-mathml, mjx-assistive-mml, annotation, script").forEach((n) => n.remove());
      const t = (clone.textContent || "").replace(/\s+/g, " ").trim();
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

  // 6. 代码块里的 LaTeX 源码（教程类文章：知乎/腾讯云等把公式写在代码块里不渲染）。
  // 优先级最低：真渲染的公式前面都已捕获，这里只补未渲染的源码型页面。
  const LATEX_CMD = /\\(?:frac|dfrac|tfrac|sqrt|sum|prod|int|iint|iiint|oint|lim|infty|partial|nabla|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|omega|phi|psi|mathbb|mathcal|mathrm|mathbf|text|displaystyle|begin|end|left|right|cdot|times|div|pm|mp|le|ge|ne|approx|equiv|over|overline|underline|hat|vec|bar|tilde|prime|sin|cos|tan|log|ln|exp|to|Rightarrow|forall|exists|in|subset|cup|cap)\b/;
  const DOLLAR_SEG = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$/g;
  const ENV_SEG = /\\begin\{(math|displaymath|equation\*?|align\*?|gather\*?|eqnarray\*?)\}([\s\S]*?)\\end\{\1\}/g;
  document.querySelectorAll("pre, code:not(pre code)").forEach((block) => {
    // 去掉注释行（教程代码块常用 # 注释），避免把注释里的说明当公式
    const raw = (block.textContent || "")
      .split("\n")
      .filter((l) => !l.trim().startsWith("#"))
      .join("\n");
    if (!raw.trim() || raw.length > 4000 || !LATEX_CMD.test(raw)) return;
    let m;
    DOLLAR_SEG.lastIndex = 0;
    while ((m = DOLLAR_SEG.exec(raw)) !== null) {
      push(m[1] || m[2] || m[3], "代码块中的 LaTeX 源码", "latex", block);
    }
    ENV_SEG.lastIndex = 0;
    while ((m = ENV_SEG.exec(raw)) !== null) {
      push(m[2], "代码块中的 LaTeX 源码", "latex", block);
    }
  });

  // 7. 正文里的纯文本公式（视觉公式/ASCII 记号/化学式嵌在文字中，如插件自带测试页场景六七）。
  // 标记驱动低误报：sqrt(/log_/上下标/±∫√ 等，以及 H2O 类简单元素式；
  // 捕获整段交给后端 normalize 转译，不自行截取。
  const MATH_MARK = /sqrt\s*\(|log_[0-9A-Za-z]|[A-Za-z0-9)\]]\^[A-Za-z0-9({−-]|[A-Za-z0-9]_[A-Za-z0-9({]|[±∫∮∑∏√∞≠≤≥≈∈⊂∂π]|\b[A-Z][a-z]?\d(?=[A-Z,，、。\s]|$)/;
  document.querySelectorAll("p, li").forEach((para) => {
    const t = (para.innerText || "").replace(/\s+/g, " ").trim();
    if (!t || t.length > 500 || !MATH_MARK.test(t)) return;
    push(t, "正文中的纯文本公式", "text", para);
  });

  return found;
})();
