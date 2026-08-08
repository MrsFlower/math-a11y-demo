// 页面公式提取脚本：由面板通过 chrome.scripting.executeScript 按需注入，
// 不常驻页面（避免干扰读屏）。整个文件是一个 IIFE，返回值即注入结果。
//
// 设计目标：页面适配器彼此隔离，统一输出候选模型。后续真实页面失败时，
// 优先新增/修正 extractor，而不是继续把规则堆进一段大流程。
//
// 返回候选：
// {
//   latex,        // 兼容旧侧边栏字段；值等于 normalized
//   raw,          // 原始提取内容
//   normalized,   // 去掉 displaystyle 等轻量清洗后的内容
//   kind,         // "latex" | "text"
//   source,       // 面向用户的来源说明
//   confidence,   // "high" | "medium" | "low"
//   context,      // 周边正文，供后端消歧义
//   debug         // 面向开发者的来源诊断信息
// }
(() => {
  const MAX = 60;
  const found = [];
  const seen = new Set();

  const LATEX_CMD = /\\(?:frac|dfrac|tfrac|sqrt|sum|prod|int|iint|iiint|oint|lim|infty|partial|nabla|alpha|beta|gamma|delta|epsilon|theta|lambda|mu|pi|sigma|omega|phi|psi|mathbb|mathcal|mathrm|mathbf|text|displaystyle|begin|end|left|right|cdot|times|div|pm|mp|le|ge|ne|approx|equiv|over|overline|underline|hat|vec|bar|tilde|prime|sin|cos|tan|log|ln|exp|to|Rightarrow|forall|exists|in|subset|cup|cap)\b/;
  const DOLLAR_SEG = /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\$([^$\n]+?)\$/g;
  const ENV_SEG = /\\begin\{(math|displaymath|equation\*?|align\*?|gather\*?|eqnarray\*?)\}([\s\S]*?)\\end\{\1\}/g;
  const MATH_MARK = /sqrt\s*\(|log_[0-9A-Za-z]|[A-Za-z0-9)\]]\^[A-Za-z0-9({−-]|[A-Za-z0-9]_[A-Za-z0-9({]|[±∫∮∑∏√∞≠≤≥≈∈⊂∂π]|\b[A-Z][a-z]?\d(?=[A-Z,，、。\s]|$)/;

  function compactText(text) {
    return (text || "").replace(/\s+/g, " ").trim();
  }

  function normalizeFormula(raw) {
    return (raw || "").replace(/^\s*\\displaystyle\s*/, "").trim();
  }

  function tagOf(el) {
    if (!el || !el.tagName) return "";
    const cls = el.className && typeof el.className === "string" ? "." + el.className.trim().split(/\s+/).slice(0, 3).join(".") : "";
    return `${el.tagName.toLowerCase()}${cls}`;
  }

  function stripAssistiveMath(root) {
    root.querySelectorAll(".katex-mathml, mjx-assistive-mml, annotation, script").forEach((n) => n.remove());
  }

  // 往上找最近的、有足够正文的祖先（段落级），截取其文字作为上下文。
  function contextOf(el) {
    const own = compactText(el && el.textContent);
    let node = el;
    for (let i = 0; i < 8 && node && node.parentElement; i++) {
      node = node.parentElement;
      if (node.tagName === "BODY" || node.tagName === "HTML") break;
      const clone = node.cloneNode(true);
      stripAssistiveMath(clone);
      const text = compactText(clone.textContent);
      const extra = own && text.includes(own) ? text.length - own.length : text.length;
      if (extra >= 30) return text.slice(0, 400);
    }
    return "";
  }

  function pushCandidate({ raw, source, kind, el, confidence, extractor, reason }) {
    if (found.length >= MAX) return;
    const normalized = normalizeFormula(raw);
    if (!normalized || normalized.length > 2000 || seen.has(normalized)) return;
    seen.add(normalized);
    found.push({
      latex: normalized,
      raw: raw || "",
      normalized,
      kind,
      source,
      confidence: confidence || (kind === "latex" ? "high" : "medium"),
      context: el ? contextOf(el) : "",
      debug: {
        extractor,
        reason: reason || "",
        tag: tagOf(el),
        rawLength: (raw || "").length,
      },
    });
  }

  function extractKatexAndMathJaxAnnotation() {
    document.querySelectorAll('annotation[encoding="application/x-tex"]').forEach((a) => {
      pushCandidate({
        raw: a.textContent,
        source: "页面自带 LaTeX 源码",
        kind: "latex",
        confidence: "high",
        extractor: "annotation-x-tex",
        reason: "KaTeX/MathJax annotation",
        el: a,
      });
    });
  }

  function extractMathJaxV2Scripts() {
    document.querySelectorAll('script[type^="math/tex"]').forEach((s) => {
      pushCandidate({
        raw: s.textContent,
        source: "页面自带 LaTeX 源码（MathJax）",
        kind: "latex",
        confidence: "high",
        extractor: "mathjax-v2-script",
        reason: s.getAttribute("type") || "",
        el: s,
      });
    });
  }

  function extractWikiImageAlt() {
    document
      .querySelectorAll("img.mwe-math-fallback-image-inline, img.mwe-math-fallback-image-display")
      .forEach((img) => {
        pushCandidate({
          raw: img.alt,
          source: "维基百科公式图替代文本",
          kind: "latex",
          confidence: "high",
          extractor: "wiki-math-img-alt",
          reason: "img alt",
          el: img,
        });
      });
  }

  function extractMathML() {
    document.querySelectorAll("math").forEach((m) => {
      if (m.querySelector('annotation[encoding="application/x-tex"]')) return;
      const alt = m.getAttribute("alttext");
      if (alt) {
        pushCandidate({
          raw: alt,
          source: "MathML alttext 属性",
          kind: "latex",
          confidence: "high",
          extractor: "mathml-alttext",
          reason: "alttext",
          el: m,
        });
        return;
      }
      pushCandidate({
        raw: m.textContent,
        source: "MathML 文本（无源码，需转换确认）",
        kind: "text",
        confidence: "medium",
        extractor: "mathml-text",
        reason: "no alttext or annotation",
        el: m,
      });
    });
  }

  function extractCodeLatex() {
    document.querySelectorAll("pre, code").forEach((block) => {
      if (block.tagName === "CODE" && block.closest("pre")) return;
      const raw = (block.textContent || "")
        .split("\n")
        .filter((line) => !line.trim().startsWith("#"))
        .join("\n");
      if (!raw.trim() || raw.length > 4000 || !LATEX_CMD.test(raw)) return;

      let match;
      DOLLAR_SEG.lastIndex = 0;
      while ((match = DOLLAR_SEG.exec(raw)) !== null) {
        pushCandidate({
          raw: match[1] || match[2] || match[3],
          source: "代码块中的 LaTeX 源码",
          kind: "latex",
          confidence: "medium",
          extractor: "code-latex-delimiter",
          reason: "dollar/bracket delimiter",
          el: block,
        });
      }

      ENV_SEG.lastIndex = 0;
      while ((match = ENV_SEG.exec(raw)) !== null) {
        pushCandidate({
          raw: match[2],
          source: "代码块中的 LaTeX 源码",
          kind: "latex",
          confidence: "medium",
          extractor: "code-latex-env",
          reason: `begin{${match[1]}}`,
          el: block,
        });
      }
    });
  }

  function extractPlainTextMath() {
    document.querySelectorAll("p, li").forEach((para) => {
      const text = compactText(para.innerText || para.textContent);
      if (!text || text.length > 500 || !MATH_MARK.test(text)) return;
      pushCandidate({
        raw: text,
        source: "正文中的纯文本公式",
        kind: "text",
        confidence: "low",
        extractor: "plain-text-math",
        reason: "math marker regex",
        el: para,
      });
    });
  }

  [
    extractKatexAndMathJaxAnnotation,
    extractMathJaxV2Scripts,
    extractWikiImageAlt,
    extractMathML,
    extractCodeLatex,
    extractPlainTextMath,
  ].forEach((extractor) => extractor());

  return found;
})();
