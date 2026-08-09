// 选区清洗（快捷键 / 面板按钮 / 右键捕获三条路径共用，经 chrome.scripting files 注入）。
// 不能直接 getSelection().toString()：KaTeX 渲染的公式被选中时，
// 隐藏的 MathML 读屏层会逐字泄进选区（「𝑥\n=\n−\n𝑏…」双层乱码），
// 后端规则全部失配。这里克隆选区，把渲染公式容器替换成 $LaTeX$ 源码；
// 拿不到源码时只剔除读屏回退层，保留视觉层文本。
//
// LaTeX 来源按优先级：
// 1. annotation[encoding="application/x-tex"]（KaTeX/MathJax 标准源码层）
// 2. script[type*="math"]（MathJax v2）
// 3. katexHtmlToTex：逆解析 KaTeX 视觉层 DOM 重建 LaTeX（AI Studio 这类
//    不带 annotation 的站点）。视觉层只有定位样式没有语义，靠 vlist 的
//    top 偏移分上下标、按 top 高低分分子分母——尽力而为，失败回退纯文本。
(() => {
  const sel = window.getSelection();
  if (!sel.rangeCount) return "";
  const holder = document.createElement("div");
  holder.appendChild(sel.getRangeAt(0).cloneContents());
  // 块级边界插换行占位：否则选项列表（A/B/C/D）会连成一串
  const BLOCKS = new Set(["P", "LI", "DIV", "UL", "OL", "TR", "BR", "H1", "H2", "H3", "H4", "SECTION", "ARTICLE", "BLOCKQUOTE", "PRE"]);
  holder.querySelectorAll("*").forEach((n) => {
    if (BLOCKS.has(n.tagName)) n.insertAdjacentText("afterend", "\n");
  });

  // ---------- KaTeX 视觉层 DOM -> LaTeX ----------
  const TOP_RE = /(^|;)\s*top:\s*(-?[\d.]+)em/;
  const topEm = (el) => {
    const m = (el.getAttribute("style") || "").match(TOP_RE);
    return m ? parseFloat(m[2]) : 0;
  };
  // KaTeX 视觉字符 -> 后端规则能吃的记号（只收读屏不友好的，其余原样）
  const CHAR_MAP = {
    "−": "-", "×": "\\times ", "÷": "\\div ", "±": "\\pm ", "∓": "\\mp ",
    "⋅": "\\cdot ", "≤": "\\le ", "≥": "\\ge ", "≠": "\\ne ", "≈": "\\approx ",
    "≡": "\\equiv ", "→": "\\to ", "←": "\\gets ", "∞": "\\infty ",
    "∂": "\\partial ", "∇": "\\nabla ", "∈": "\\in ", "∉": "\\notin ",
    "⊂": "\\subset ", "⊆": "\\subseteq ", "∪": "\\cup ", "∩": "\\cap ",
    "∫": "\\int ", "∬": "\\iint ", "∭": "\\iiint ", "∮": "\\oint ",
    "∑": "\\sum ", "∏": "\\prod ", "√": "\\sqrt ", "∠": "\\angle ",
    "⊥": "\\perp ", "∥": "\\parallel ", "…": "\\ldots ", "′": "'",
    "α": "\\alpha ", "β": "\\beta ", "γ": "\\gamma ", "δ": "\\delta ",
    "θ": "\\theta ", "λ": "\\lambda ", "μ": "\\mu ", "π": "\\pi ",
    "ρ": "\\rho ", "σ": "\\sigma ", "ω": "\\omega ", "φ": "\\phi ",
    "Δ": "\\Delta ", "Ω": "\\Omega ",
  };
  const FUNC_NAMES = new Set(["sin", "cos", "tan", "cot", "sec", "csc", "arcsin",
    "arccos", "arctan", "sinh", "cosh", "tanh", "ln", "log", "exp", "lim",
    "max", "min", "sup", "inf", "det", "deg", "gcd", "arg"]);
  const SKIP = new Set(["strut", "pstrut", "svg", "vlist-s"]);

  function katexChildren(nodes, skipMfrac) {
    let out = "";
    nodes.forEach((n) => { out += katexNode(n, skipMfrac); });
    return out;
  }

  function katexScripts(msupsub) {
    let out = "";
    msupsub.querySelectorAll(":scope > .vlist-t").forEach((vt) => {
      let sup = "", sub = "";
      vt.querySelectorAll(":scope > .vlist-r > .vlist > span").forEach((lvl) => {
        const t = topEm(lvl);
        const content = katexChildren(Array.from(lvl.childNodes));
        if (!content) return;
        if (t <= -0.4) sup = sup || content;   // 顶得越高（top 越负）越是上标
        else sub = sub || content;
      });
      // 兜底：整块没解析出偏移时按 DOM 顺序当上标（KaTeX 上标在前）
      if (!sup && !sub) {
        const t = vt.textContent.trim();
        if (t) sup = katexChildren(Array.from(vt.childNodes));
      }
      if (sub) out += "_{" + sub + "}";
      if (sup) out += "^{" + sup + "}";
    });
    return out;
  }

  function katexFrac(mfrac) {
    const cells = [];
    mfrac.querySelectorAll(":scope > .vlist-t > .vlist-r > .vlist > span").forEach((lvl) => {
      const t = topEm(lvl);
      // KaTeX 常给分子/分母再包一层 .mfrac 定位包裹：递归时跳过它，
      // 否则会被当成嵌套分式解析成空
      cells.push({ t, s: katexChildren(Array.from(lvl.childNodes), true) });
    });
    cells.sort((a, b) => a.t - b.t); // top 越负位置越高：最负的是分子
    const filled = cells.filter((c) => c.s.trim()); // 排除 frac-line 这类空层
    const num = filled[0] ? filled[0].s : "";
    const den = filled[1] ? filled[1].s : "";
    if (!num && !den) return "";
    return "\\frac{" + num + "}{" + den + "}";
  }

  function katexSqrt(msqrt) {
    const body = msqrt.querySelector(".sqrt-body");
    const inner = body ? katexChildren(Array.from(body.childNodes)) : "";
    return inner ? "\\sqrt{" + inner + "}" : "";
  }

  function katexDelims(el) {
    // \left…\right 的定界符：成对补 \left \right，孤立的按普通括号
    const parts = [];
    Array.from(el.children).forEach((c) => {
      if (c.classList.contains("nulldelimiter")) return;
      if (c.classList.contains("mopen") || c.classList.contains("mclose")) {
        const t = (c.textContent || "").trim();
        const isSized = c.querySelector(".delimcenter") || /left|right/.test(c.className);
        parts.push({ t, sized: !!isSized, open: c.classList.contains("mopen") });
      } else if (!SKIP.has(c.classList[0] || "")) {
        parts.push({ other: katexNode(c) });
      }
    });
    let out = "";
    parts.forEach((p) => {
      if (p.other !== undefined) { out += p.other; return; }
      if (p.sized) out += (p.open ? "\\left " : "\\right ") + p.t + " ";
      else out += p.t;
    });
    return out;
  }

  function katexNode(n, skipMfrac) {
    if (n.nodeType === 3) {
      const t = n.textContent;
      return CHAR_MAP[t] !== undefined ? CHAR_MAP[t] : t;
    }
    if (!n.classList) return "";
    const cls = Array.from(n.classList);
    const has = (c) => cls.includes(c);
    if (cls.some((c) => SKIP.has(c))) return "";
    if (has("mspace")) return " ";
    if (has("msupsub")) return katexScripts(n);
    if (has("mfrac") && !skipMfrac) return katexFrac(n);
    if (has("msqrt") || has("root")) return katexSqrt(n);
    if (has("accent")) {
      // \vec/\hat/\bar 等：取基底文本近似（读屏场景重结构轻修饰）
      const base = n.querySelector(".accent-body");
      const body = n.textContent || "";
      return base ? body.replace(base.textContent, "") : body;
    }
    if (has("mop")) {
      const t = (n.textContent || "").trim();
      return FUNC_NAMES.has(t) ? "\\" + t + " " : (CHAR_MAP[t] !== undefined ? CHAR_MAP[t] : t + " ");
    }
    if (has("mopen") || has("mclose")) return katexDelims(n);
    if (has("base") || has("mord")) {
      // mord 可能是「单字符」也可能是「base+msupsub 的包裹体」，一律走子节点
      return katexChildren(Array.from(n.childNodes));
    }
    return katexChildren(Array.from(n.childNodes));
  }

  function katexHtmlToTex(katexEl) {
    const html = katexEl.querySelector(".katex-html");
    const out = html ? katexChildren(Array.from(html.childNodes)) : "";
    return out.replace(/\s+/g, " ").trim();
  }

  const texOf = (root) => {
    const ann = root.querySelector('annotation[encoding="application/x-tex"]');
    if (ann && ann.textContent.trim()) return ann.textContent.trim();
    const scr = root.querySelector('script[type*="math"]');
    if (scr && scr.textContent.trim()) return scr.textContent.trim();
    // MathJax v2：源码 script[type="math/tex"] 与渲染容器是相邻兄弟节点
    // （script 在前、输出在后），不在容器内部。只克隆到容器时拿不到源码，
    // 只能剩拍平的视觉文本（广义积分会变「∫1+∞x21dx」这类乱码）；
    // 补看相邻 script，与页面提取（整页扫 script）对齐
    for (const nb of [root.previousElementSibling, root.nextElementSibling]) {
      if (nb && nb.tagName === "SCRIPT" && /math/.test(nb.getAttribute("type") || "")) {
        const t = (nb.textContent || "").trim();
        if (t) return t;
      }
    }
    return "";
  };
  holder.querySelectorAll(".katex, mjx-container, .MathJax_Display, .MathJax").forEach((el) => {
    if (!holder.contains(el)) return; // 已随外层容器被替换
    let tex = texOf(el);
    if (!tex && el.classList && el.classList.contains("katex")) {
      try { tex = katexHtmlToTex(el); } catch (e) { tex = ""; } // 逆解析失败宁回退纯文本
    }
    if (tex) {
      el.replaceWith(document.createTextNode(" $" + tex + "$ "));
    } else {
      el.querySelectorAll(".katex-mathml, mjx-assistive-mml, annotation").forEach((n) => n.remove());
    }
  });
  holder.querySelectorAll("math, semantics").forEach((m) => {
    if (!holder.contains(m)) return;
    // 只选中公式左半（MathML 渲染体）时，选区克隆根是 math 而非 .katex，
    // 上面的容器分支匹配不到；这里同样优先抠 annotation 源码，保住根号等结构
    const tex = texOf(m);
    if (tex) {
      m.replaceWith(document.createTextNode(" $" + tex + "$ "));
      return;
    }
    const alt = m.getAttribute("alttext");
    if (alt) {
      m.replaceWith(document.createTextNode(" $" + alt + "$ "));
    } else {
      m.querySelectorAll("mjx-assistive-mml, annotation").forEach((n) => n.remove());
    }
  });
  // 公式图片（维基百科渲染失败回退图）：img 没有 textContent，
  // 不处理的话选中含图区域时公式直接丢失；alt 就是 LaTeX 源码，替换成 $alt$
  holder.querySelectorAll("img.mwe-math-fallback-image-inline, img.mwe-math-fallback-image-display").forEach((img) => {
    if (!holder.contains(img)) return;
    const alt = (img.getAttribute("alt") || "").trim();
    if (alt) img.replaceWith(document.createTextNode(" $" + alt + "$ "));
  });
  // 脚本内容永远不属于选区可读文本：真实页面里 script 不可被选中，
  // 克隆里出现只可能是 MathJax v2 的源码层（tex 已被相邻容器消费），
  // 不剔除会把源码重复拼进结果
  holder.querySelectorAll("script").forEach((s) => s.remove());
  return (holder.textContent || "")
    .split("\n")
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
})();
