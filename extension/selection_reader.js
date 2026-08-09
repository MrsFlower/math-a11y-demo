// 选区清洗（快捷键 / 面板按钮 / 右键捕获三条路径共用，经 chrome.scripting files 注入）。
// 不能直接 getSelection().toString()：KaTeX 渲染的公式被选中时，
// 隐藏的 MathML 读屏层会逐字泄进选区（「𝑥\n=\n−\n𝑏…」双层乱码），
// 后端规则全部失配。这里克隆选区，把渲染公式容器替换成 $LaTeX$ 源码；
// 拿不到源码时只剔除读屏回退层，保留视觉层文本。
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
  const texOf = (root) => {
    const ann = root.querySelector('annotation[encoding="application/x-tex"]');
    if (ann && ann.textContent.trim()) return ann.textContent.trim();
    const scr = root.querySelector('script[type*="math"]');
    if (scr && scr.textContent.trim()) return scr.textContent.trim();
    return "";
  };
  holder.querySelectorAll(".katex, mjx-container, .MathJax_Display, .MathJax").forEach((el) => {
    if (!holder.contains(el)) return; // 已随外层容器被替换
    const tex = texOf(el);
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
  return (holder.textContent || "")
    .split("\n")
    .map((s) => s.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
})();
