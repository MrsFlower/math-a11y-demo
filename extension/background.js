// 后台 service worker：只做触发路由（右键菜单 / 快捷键 → 侧边栏），不碰业务逻辑。
// 捕获内容通过 chrome.storage.session 传给面板：面板可能尚未加载，
// 加载后自取；已加载时再补一条运行时消息即时刷新。

const MENU_ID = "math-a11y-process-selection";
const SHORTCUT_PREF_KEY = "math_a11y_shortcut_prefs_v1";

chrome.runtime.onInstalled.addListener(() => {
  // 点工具栏图标 = 开/关侧边栏
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true });
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "用公式助手处理选中内容",
    contexts: ["selection"],
  });
});

// 把捕获内容交给面板（storage.session 兜底 + 消息即时通知）
async function deliverCapture(payload) {
  await chrome.storage.session.set({ pendingCapture: payload });
  try {
    await chrome.runtime.sendMessage({ type: "capture", payload });
  } catch (e) {
    // 面板未打开时没有接收方，属正常；面板加载时会从 storage.session 自取。
  }
}

async function deliverShortcutAction(action) {
  await chrome.storage.session.set({ pendingShortcutAction: action });
  try {
    await chrome.runtime.sendMessage({ type: "shortcut-action", action });
  } catch (e) {
    // 面板未打开时没有接收方，属正常；面板加载时会从 storage.session 自取。
  }
}

async function loadShortcutPrefs() {
  const obj = await chrome.storage.local.get(SHORTCUT_PREF_KEY);
  return obj[SHORTCUT_PREF_KEY] || { setupDone: false };
}

async function readSelection(tab) {
  const [ret] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    // 不能直接 getSelection().toString()：KaTeX 渲染的公式被选中时，
    // 隐藏的 MathML 读屏层会逐字泄进选区（「𝑥\n→\n0\nx→0」双层乱码），
    // 后端规则全部失配。这里克隆选区，把渲染公式容器替换成 $LaTeX$ 源码；
    // 拿不到源码时只剔除读屏回退层，保留视觉层文本。
    func: () => {
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
      holder.querySelectorAll("math").forEach((m) => {
        if (!holder.contains(m)) return;
        const alt = m.getAttribute("alttext");
        if (alt) {
          m.replaceWith(document.createTextNode(" $" + alt + "$ "));
        } else {
          m.querySelectorAll("mjx-assistive-mml, annotation").forEach((n) => n.remove());
        }
      });
      return (holder.textContent || "")
        .split("\n")
        .map((s) => s.replace(/\s+/g, " ").trim())
        .filter(Boolean)
        .join("\n");
    },
  });
  return (ret && ret.result || "").trim();
}

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== MENU_ID || !tab) return;
  // open() 必须留在用户手势调用栈内，先开面板再投递内容
  chrome.sidePanel.open({ tabId: tab.id });
  deliverCapture({
    kind: "selection",
    text: info.selectionText || "",
    time: Date.now(),
  });
});

chrome.commands.onCommand.addListener(async (command, cmdTab) => {
  if (command !== "capture-selection") return;
  console.log("[公式助手] 快捷键触发:", command);
  // open() 必须在手势调用栈内同步调用：不能先 await，
  // 直接用 onCommand 第二参带回的活动 tab
  const tab = cmdTab || await chrome.tabs.query({ active: true, currentWindow: true }).then(r => r[0]);
  if (!tab) {
    chrome.storage.local.set({ __shortcut_debug: { stage: "no-tab", time: Date.now() } });
    return;
  }
  try {
    chrome.sidePanel.open({ tabId: tab.id }).catch((e) => {
      console.error("[公式助手] sidePanel.open 失败:", e);
      chrome.storage.local.set({ __shortcut_debug: {
        stage: "open-failed", error: String(e && e.message || e),
        tabId: tab.id, url: (tab.url || "").slice(0, 80), time: Date.now() } });
    });
    chrome.storage.local.set({ __shortcut_debug: {
      stage: "open-called", tabId: tab.id,
      url: (tab.url || "").slice(0, 80), time: Date.now() } });
  } catch (e) {
    chrome.storage.local.set({ __shortcut_debug: {
      stage: "open-throw", error: String(e && e.message || e), time: Date.now() } });
  }

  const prefs = await loadShortcutPrefs();
  if (!prefs.setupDone) {
    deliverShortcutAction({ kind: "open_setup", time: Date.now() });
    return;
  }

  if (prefs.shortcutMode === "explain_scan") {
    deliverShortcutAction({ kind: "shortcut_explain_scan", time: Date.now() });
    return;
  }

  if (prefs.shortcutMode === "text_input") {
    deliverShortcutAction({ kind: "shortcut_text_input", time: Date.now() });
    return;
  }

  try {
    const text = await readSelection(tab);
    if (text) {
      deliverShortcutAction({ kind: "shortcut_selection", text, time: Date.now() });
    } else {
      deliverShortcutAction({ kind: "shortcut_empty_selection", time: Date.now() });
    }
  } catch (e) {
    deliverShortcutAction({ kind: "shortcut_restricted_page", message: e.message || String(e), time: Date.now() });
  }
});
