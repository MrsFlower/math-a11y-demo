// 侧边面板任务流：首页（送入内容）→ 转译结果 → 进一步讲解 → 追问 → 历史。
// 不向用户暴露「模式」：转译是默认动作，讲解从结果页一键进入；
// 识别置信度高直接开讲，中低才弹出确认区（确认区在主内容区，不在折叠里）。
// 所有状态变化都写入 #status（aria-live），读屏自动播报。

// 默认连云端（百炼高代码应用 FC 触发器），用户开箱即用；
// 也可在底部「服务设置」改回本机 http://127.0.0.1:8321
const DEFAULT_API = "https://highcodzteceggb-azvgiimdkb.cn-beijing.fcapp.run";
// FC 触发器鉴权 token（无 Authorization 头会被网关拒绝）；对本地服务附带无副作用。
// 开源版为占位符：请替换为你自己的 FC 触发器 token，或在「服务设置」改指向本地服务。
const DEFAULT_TOKEN = "YOUR_FC_TRIGGER_TOKEN";
const API_KEY = "math_a11y_api_base_v1";
const PROFILE_KEY = "math_a11y_transcribe_profile_v1";
const EXPLAIN_VOICE_KEY = "math_a11y_explain_voice_v1";
const FRACTION_STYLE_KEY = "math_a11y_fraction_style_v1";
const HISTORY_KEY = "math_a11y_history_v1";
const SHORTCUT_PREF_KEY = "math_a11y_shortcut_prefs_v1";
const $ = (id) => document.getElementById(id);

function authHeaders() {
  return DEFAULT_TOKEN ? { Authorization: `Bearer ${DEFAULT_TOKEN}` } : {};
}

// 服务地址可配置（默认云端；可在「服务设置」改回本机）
function apiBase() {
  let v = "";
  try { v = localStorage.getItem(API_KEY) || ""; } catch (e) { /* 忽略 */ }
  v = v.trim().replace(/\/+$/, "");
  return v || DEFAULT_API;
}

let currentLatex = "";       // 已确认并分析的公式
let currentData = null;      // 最近一次分析结果
let abortCtrl = null;
let candidateItems = [];     // 当前候选列表（供数字键直选）
let pendingContext = "";     // 公式所在页面的上下文（仅提取入口有，供后端消歧义）
let pendingRetry = null;     // 授权成功后要重试的动作（自愈授权流程用）

// ---------------- 状态与工具 ----------------

// 页面注入失败的分类诊断（分类依据见 scripts/_diag_restricted_pages.py 复现结论）
function classifyInjectError(msg, tabUrl) {
  const m = String(msg || "");
  const u = String(tabUrl || "");
  if (/^edge:\/\/|^chrome:\/\//i.test(u) || /Cannot access (a )?(chrome|edge):/i.test(m)) {
    return "当前是浏览器内置页面（edge:// 或 chrome:// 开头），插件无法读取。请切换到普通网页；也可以手动复制内容后到这里粘贴。";
  }
  if (/gallery cannot be scripted/i.test(m)) {
    return "当前是新标签页或扩展商店页面，插件无法在此运行。请切换到普通网页后再提取。";
  }
  if (/^data:/i.test(u)) {
    return "当前是 data: 临时页面，不支持插件注入。请直接粘贴内容转译。";
  }
  if (/^file:/i.test(u)) {
    return "当前是本地文件页面。请到扩展管理页（edge://extensions）找到本插件，打开「允许访问文件网址」后重试；也可以直接粘贴内容。";
  }
  if (/Cannot access contents of the page/i.test(m)) {
    return "插件还没拿到这个页面的访问授权。请先点一下浏览器工具栏上的插件图标（授权当前页面），再按一次刚才的按钮；还不行就关掉侧边栏重新打开。";
  }
  return "注入失败原因未识别。请展开底部「服务设置」按「运行诊断」，把结果发给开发者。";
}

// 是否为 activeTab 授权缺失（自愈授权流程的触发条件）
function isAuthMissingError(msg) {
  return /Cannot access contents of the page/i.test(String(msg || ""));
}

// 自愈授权：注入因授权缺失失败时，给出引导并展示「授权并重试」按钮。
// 全程读屏可达：状态区播报下一步，焦点落在按钮上，回车即触发系统授权对话框。
function offerAuthGrant(retryFn) {
  pendingRetry = retryFn;
  setStatus("插件没有权限读取这个页面。焦点已在「授权插件读取网页并重试」按钮：按回车后浏览器会弹出授权对话框，请按读屏提示在对话框里确认允许；授权成功后会自动重试刚才的操作。不想授权的话，也可以直接粘贴内容。", "error");
  const btn = $("auth-grant-btn");
  btn.hidden = false;
  btn.focus();
}

function setStatus(msg, kind) {
  const el = $("status");
  el.textContent = msg;
  if (kind === "error") el.dataset.kind = "error";
  else delete el.dataset.kind;
  // 新状态出现时，上一次断连留下的「一键恢复云端」按钮同步收起，避免旧按钮误导
  $("cloud-reset-btn").hidden = true;
  $("auth-grant-btn").hidden = true;
}

function focusStatus() {
  const el = $("status");
  el.setAttribute("tabindex", "-1"); // html 里也带了 tabindex，此处双保险
  el.focus();
}

// 忙碌状态反馈：按钮进入「处理中」时的统一入口。
// 旧行为：点击后焦点停在按钮上，按钮随即被禁用，读屏补播「不可用」，
// 用户分不清操作是否已受理。现改为：按钮文案换成进行中语义 + 状态区
// 播报 + 焦点移到状态区，读屏直接读到「正在…」而不是「不可用」。
function enterBusyState(btn, busyText, statusMsg) {
  if (btn) {
    btn.textContent = busyText; // Tab 回来摸到的也是明确状态
    if (btn.hasAttribute("aria-label")) btn.setAttribute("aria-label", busyText);
    btn.disabled = true;
  }
  setStatus(statusMsg);
  focusStatus();
}

function looksLikeLatex(text) {
  // 含非 ASCII 数学符号（±、×、√、π 等）或 sqrt 这类口语写法 → 不是规范 LaTeX，先走转换
  if (/[±×÷√∞π≠≤≥∫∬∭∮∑∏∂∇αβγδθλμρστωΩ−]/.test(text) || /\bsqrt\s*\(/.test(text)) return false;
  return /\\[a-zA-Z]+/.test(text) || /[\^_{}]/.test(text);
}

async function copyText(text, label) {
  try {
    await navigator.clipboard.writeText(text);
    setStatus(`${label}已复制到剪贴板。`);
  } catch (e) {
    setStatus(`复制失败：${e.message}。内容仍显示在结果区，可自行选中后按 Ctrl+C。`, "error");
  }
}

async function apiPost(path, body, signal) {
  const resp = await fetch(apiBase() + path, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
    signal,
  });
  return resp.json();
}

function backendDownMsg(e) {
  // 把真实失败原因带出来，便于远程定位：网络失败显示 Failed to fetch，
  // 鉴权被拒显示 HTTP 400，而不是统统归成一句套话
  let reason = "";
  if (e) {
    if (e.status) reason = `，错误：HTTP ${e.status}`;
    else if (e.message) reason = `，错误：${e.message}`;
  }
  return `无法连接理解服务（${apiBase()}）${reason}。请检查网络连接；按「恢复默认云端服务」按钮可一键还原；也可在底部「服务设置」里换一个可用的服务地址（本机服务为 http://127.0.0.1:8321）。`;
}

// 后端断连统一播报：除错误文案外显出「一键恢复云端」修复动作；
// 操作中失败时焦点直接落到修复按钮，读屏用户按 Enter 即可自救
function announceBackendDown(e, focusFix = true) {
  setStatus(backendDownMsg(e), "error");
  const btn = $("cloud-reset-btn");
  btn.hidden = false;
  if (focusFix) btn.focus();
}

// ---------------- 转译风格（状态内部化：不再用可见的单选框） ----------------
// 风格切换入口在转译结果页的「换朗读风格」按钮：用户听完结果再决定换，
// 切换后立即重转并播报后果，不预先设置。

function currentTranscribeProfile() {
  try {
    const v = localStorage.getItem(PROFILE_KEY);
    if (v === "unicode_compact" || v === "spoken_structured") return v;
  } catch (e) { /* 忽略 */ }
  return "spoken_structured";
}

function profileName(p) {
  return p === "unicode_compact" ? "紧凑文本" : "结构朗读";
}

// 分式读法偏好：structured=「分数，分子是…」（默认）/ compact=「分母 分之 分子」。
// 讲解链路专用（parse-latex 的 fraction_style 参数），不影响转译风格。
function currentFractionStyle() {
  try {
    const v = localStorage.getItem(FRACTION_STYLE_KEY);
    if (v === "compact" || v === "structured") return v;
  } catch (e) { /* 忽略 */ }
  return "structured";
}

function radioValue(name, fallback) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : fallback;
}

function setRadioValue(name, value) {
  const el = document.querySelector(`input[name="${name}"][value="${value}"]`);
  if (el) el.checked = true;
}

async function loadShortcutPrefs() {
  const obj = await chrome.storage.local.get(SHORTCUT_PREF_KEY);
  return obj[SHORTCUT_PREF_KEY] || {
    setupDone: false,
    shortcutMode: "selection_transcribe",
    transcribeProfile: "spoken_structured",
  };
}

async function saveShortcutPrefs(prefs) {
  await chrome.storage.local.set({ [SHORTCUT_PREF_KEY]: prefs });
}

function applyShortcutPrefsToControls(prefs) {
  setRadioValue("shortcut-mode", prefs.shortcutMode || "selection_transcribe");
  setRadioValue("shortcut-profile", prefs.transcribeProfile || "spoken_structured");
  $("shortcut-remember").checked = prefs.setupDone !== false;
}

function applyShortcutPrefsToState(prefs) {
  updateQuickStart(prefs);
}

function shortcutModeLabel(prefs) {
  if (prefs.shortcutMode === "explain_scan") return "扫描当前页面公式并逐条讲解";
  if (prefs.shortcutMode === "text_input") return "打开文本输入框等待粘贴";
  const profile = prefs.transcribeProfile === "unicode_compact" ? "紧凑文本" : "结构朗读";
  return `转译当前选中公式并输出${profile}`;
}

function primaryActionLabel(prefs) {
  if (prefs.shortcutMode === "explain_scan") return "扫描并理解本页公式";
  if (prefs.shortcutMode === "text_input") return "粘贴公式";
  return "转译选中公式";
}

function updateQuickStart(prefs) {
  const p = prefs || {
    setupDone: false,
    shortcutMode: "selection_transcribe",
    transcribeProfile: "spoken_structured",
  };
  const setup = p.setupDone ? "已保存" : "未保存";
  $("shortcut-summary").textContent = `Ctrl+Shift+M 当前默认：${shortcutModeLabel(p)}（${setup}）。`;
  $("primary-action-btn").textContent = primaryActionLabel(p);
  $("primary-action-btn").setAttribute("aria-label", `${primaryActionLabel(p)}。${$("shortcut-summary").textContent}`);
}

function showMainWorkflow() {
  $("quick-start").hidden = false;
  $("alternate-actions").hidden = false;
}

function hideMainWorkflow() {
  $("quick-start").hidden = true;
  $("alternate-actions").hidden = true;
}

async function showShortcutSetup(reason) {
  const prefs = await loadShortcutPrefs();
  applyShortcutPrefsToControls(prefs);
  hideMainWorkflow();
  $("shortcut-setup").hidden = false;
  const prefix = reason || "请选择 Ctrl+Shift+M 的默认行为。";
  setStatus(`${prefix}保存后，下次按快捷键会直接执行所选模式。`);
  $("shortcut-setup-heading").focus();
}

function hideShortcutSetup() {
  $("shortcut-setup").hidden = true;
  showMainWorkflow();
}

function focusTextInput(message, kind) {
  // 粘贴区已平铺在「开始」区，无需展开折叠
  $("confirm-box").hidden = true;
  $("candidates").hidden = true;
  $("transcribe-section").hidden = true;
  setStatus(message, kind);
  $("paste-input").focus();
}

async function runPrimaryAction() {
  const prefs = await loadShortcutPrefs();
  hideShortcutSetup();
  if (prefs.shortcutMode === "explain_scan") {
    setStatus("正在按默认方式扫描当前页面公式。");
    extractPage();
    return;
  }
  if (prefs.shortcutMode === "text_input") {
    focusTextInput("请粘贴题目、公式或化学式，然后按 Tab 到「转译粘贴的公式」。");
    return;
  }
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    // 与快捷键同款的选区清洗（selection_reader.js）：裸 toString 会把
    // KaTeX 隐藏读屏层泄进来，导致转译结果一半乱码一半正确
    const [ret] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["selection_reader.js"],
    });
    const text = (ret && ret.result || "").trim();
    if (text) {
      startTranscription(text, "当前页面选中内容");
    } else {
      focusTextInput("没有检测到选中内容。请先选中公式或题目区域后再点主按钮；也可以在此处粘贴文本后开始转译。", "error");
    }
  } catch (e) {
    // 不再笼统猜「内置页面」：把真实错误分类后给用户可执行的下一步；
    // 授权缺失走自愈授权流程（一次授权永久生效）
    if (isAuthMissingError(e && e.message)) {
      offerAuthGrant(() => runPrimaryAction());
      return;
    }
    focusTextInput("当前页面无法读取选中内容。" + classifyInjectError(e && e.message, tab && tab.url), "error");
  }
}

// ---------------- 识别待确认 ----------------

function enterConfirm(latex, sourceNote, confidenceNote) {
  $("candidates").hidden = true;
  $("confirm-box").hidden = false;
  $("confirm-input").value = latex;
  $("capture-source").textContent = `来源：${sourceNote}。${confidenceNote || ""}`;
  $("speech-preview").textContent = "";
  // 盲人主路径：焦点落在主操作按钮（听预览→回车），编辑是少数场景的可选路径
  setStatus(`识别结果需要确认（${sourceNote}），正在生成朗读预览。焦点已在「确认并讲解」按钮，按回车开始讲解；需修改请按 Shift+Tab 进入编辑框。`);
  $("confirm-btn").focus();
  previewSpeech(latex);
}

// 结构朗读预览：本地解析很快（不调大模型），aria-live 到达时自动播报
async function previewSpeech(latex) {
  try {
    const data = await apiPost("/api/parse-latex", { latex, with_explanation: false });
    if (data.ok && data.speech_text) {
      $("speech-preview").textContent = `朗读预览：${data.speech_text}`;
    }
  } catch (e) {
    // 预览失败不打断流程，确认时会再报具体错误
  }
}

// ---------------- 捕获入口 ----------------

// 默认路径：选中文本 / 右键捕获 → 直接转译（不解释）。
async function handleIncomingText(text, sourceNote) {
  const t = (text || "").trim();
  if (!t) {
    setStatus("没有捕获到内容。请先在页面上选中内容，或改用手动粘贴。", "error");
    return;
  }
  startTranscription(t, sourceNote);
}

// 讲解路径：把文本转成 LaTeX 后开讲。高置信度直接分析（用户无感），
// 中低置信度才弹确认区——把「确认」从必经步骤降级为异常处理。
async function explainIncomingText(text, sourceNote) {
  const t = (text || "").trim();
  if (!t) {
    setStatus("没有捕获到内容。请先在页面上选中内容，或改用手动粘贴。", "error");
    return;
  }
  if (looksLikeLatex(t)) {
    await analyzeLatex(t, sourceNote, "内容本身就是 LaTeX，识别零误差。");
    return;
  }
  setStatus("捕获到普通文本，正在转换为公式…");
  try {
    const data = await apiPost("/api/normalize-input", { text: t });
    if (data.ok && data.latex) {
      if (data.confidence === "high") {
        await analyzeLatex(data.latex, sourceNote, "已自动识别为公式。");
      } else {
        const conf = data.confidence === "medium" ? "转换置信度：中，请检查。"
          : "转换置信度：低，请仔细检查每个符号。";
        enterConfirm(data.latex, `${sourceNote}（已自动转换）`, conf + (data.notes ? ` ${data.notes}` : ""));
      }
    } else {
      setStatus(`转换失败：${data.error || "未识别出公式"}。可在「开始」区直接粘贴 LaTeX。`, "error");
    }
  } catch (e) {
    announceBackendDown(e);
  }
}

// 提取本页公式并逐条讲解（注入 content.js）
async function extractPage() {
  setStatus("正在提取本页公式…");
  $("candidates").hidden = true;
  $("confirm-box").hidden = true;
  let results;
  let tab;
  try {
    [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error("找不到当前标签页");
    [results] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (e) {
    // 保留真实错误分类：测试用户报「此页面无法提取」时可能实为 activeTab 授权失效，
    // 笼统提示会让用户误以为页面不支持；授权缺失走自愈授权流程
    if (isAuthMissingError(e && e.message)) {
      offerAuthGrant(() => extractPage());
      return;
    }
    setStatus("此页面无法提取。" + classifyInjectError(e && e.message, tab && tab.url)
      + " 仍无法解决时，展开底部「服务设置」按「运行诊断」，把结果发给开发者。", "error");
    return;
  }
  const found = (results && results.result) || [];
  if (found.length === 0) {
    $("alternate-actions").open = true;
    setStatus("当前页面没有检测到可识别的公式。请切换到包含公式的页面后再扫描；也可以先选中公式再点「转译选中公式」，或在「开始」区直接粘贴。焦点已在主按钮。", "error");
    $("primary-action-btn").focus();
    return;
  }
  if (found.length === 1) {
    routeCandidate(found[0]);
    return;
  }
  // 多个候选：并行拿中文朗读作为按钮主文本（盲人听 LaTeX 天书无法判断选哪条），LaTeX 降为副信息
  setStatus(`找到 ${found.length} 个公式，正在生成中文朗读…`);
  const speeches = await Promise.all(
    found.map(async (f) => {
      if (f.kind !== "latex") return f.latex;
      try {
        const d = await apiPost("/api/parse-latex", { latex: f.latex, with_explanation: false });
        return d.ok && d.speech_text ? d.speech_text : f.latex;
      } catch (e) {
        return f.latex;
      }
    })
  );
  const list = $("candidates-list");
  list.innerHTML = "";
  found.forEach((f, i) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.append(`${i + 1}. ${speeches[i]}`);
    if (speeches[i] !== f.latex) {
      const sub = document.createElement("span");
      sub.className = "latex-sub";
      sub.setAttribute("aria-hidden", "true"); // LaTeX 天书不进读屏，仅供明眼人核对
      sub.textContent = f.latex;
      btn.appendChild(sub);
    }
    // 路标：盲人刚读过公式旁的正文，靠它在几十条候选里认出自己那条
    const ctx = (f.context || "").slice(0, 50);
    if (ctx) {
      const cs = document.createElement("span");
      cs.className = "ctx-sub";
      cs.textContent = `附近正文：${ctx}…`;
      btn.appendChild(cs);
    }
    btn.setAttribute(
      "aria-label",
      `第 ${i + 1} 个公式：${speeches[i].slice(0, 100)}。` +
        (ctx ? `附近正文：${ctx}。` : "") +
        `来源：${f.source}`
    );
    btn.addEventListener("click", () => routeCandidate(f));
    list.appendChild(btn);
  });
  candidateItems = found;
  $("candidates").hidden = false;
  // 长列表时数字键只覆盖前 9 条，直接告诉用户用「附近正文」路标定位，
  // 避免盲用户在几十条里盲目 Tab
  const numHint = found.length > 9
    ? `按数字键 1 到 9 可选前 9 条；其余请用 Tab 逐条浏览，每条都带「附近正文」路标，听到熟悉的题干再按回车。`
    : `按数字键 1 到 ${Math.min(found.length, 9)} 直接选择，或用 Tab 浏览列表。`;
  setStatus(`找到 ${found.length} 个公式，已转成中文朗读。${numHint}`);
  $("candidates-heading").focus();
}

function routeCandidate(f) {
  pendingContext = f.context || ""; // 带上公式周围正文，帮后端判断符号含义
  // 公式列表保留在屏上：听完一条讲解还能靠「附近正文」路标换另一条，
  // 不必重新扫页；当前选中的条目用 aria-current 标出
  const idx = candidateItems.indexOf(f);
  Array.from($("candidates-list").children).forEach((btn, i) => {
    if (i === idx) btn.setAttribute("aria-current", "true");
    else btn.removeAttribute("aria-current");
  });
  if (f.kind === "latex") {
    // 页面自带 LaTeX 源码，识别零误差：不再弹确认，直接开讲
    analyzeLatex(f.latex, f.source, "页面自带源码，识别零误差。");
  } else {
    explainIncomingText(f.latex, f.source);
  }
}

// ---------------- 分析 ----------------

function setAnalyzing(on) {
  ["extract-btn", "paste-btn", "paste-explain-btn", "confirm-btn", "reextract-btn",
   "transcribe-copy-btn", "transcribe-to-explain-btn", "profile-toggle-btn",
   "transcribe-ai-retry-btn", "transcribe-edit-source-btn"].forEach(
    (id) => ($(id).disabled = on)
  );
  $("cancel-btn").hidden = !on;
  if (on) {
    // 焦点若停在刚被禁用的按钮上，读屏会补播「不可用」盖过「正在讲解」提示；
    // 移到状态区，用户直接听到调用方已播报的进行中语义
    const active = document.activeElement;
    if (active && active.tagName === "BUTTON" && active.disabled) focusStatus();
  }
}

// ---------------- 转译（第五阶段） ----------------

let lastTranscription = null; // { original, result, sourceNote, profile, confidence, warnings, source }

function renderTranscribeWarnings(list) {
  const slot = $("transcribe-warnings");
  slot.innerHTML = "";
  if (!list || !list.length) {
    slot.hidden = true;
    return;
  }
  list.forEach((w) => {
    const p = document.createElement("p");
    p.textContent = w;
    slot.appendChild(p);
  });
  slot.hidden = false;
}

function renderTranscribeFallback(data) {
  const warnings = data.warnings || [];
  const residue = data.residue || [];
  const lowConfidence = data.confidence === "low";
  // medium（零命中零残留）也要给救济入口：KaTeX 视觉层被拍平这类结构性丢失
  // 不会留下残留记号，但结果往往是错的
  const midConfidence = data.confidence === "medium";
  const needsFallback = data.source !== "llm" && (lowConfidence || midConfidence || warnings.length > 0 || residue.length > 0);
  const aiUnavailable = warnings.some((w) => String(w).includes("AI 重新转译当前不可用"));
  $("transcribe-fallback").hidden = !needsFallback;
  $("transcribe-ai-retry-btn").disabled = aiUnavailable;
  if (!needsFallback) {
    $("transcribe-fallback-reason").textContent = "";
    return;
  }
  const reasons = [];
  if (lowConfidence) reasons.push("本次转译置信度低，结果可能有误");
  if (residue.length) reasons.push(`仍有规则未覆盖的记号：${residue.join("、")}`);
  else if (warnings.length) reasons.push(warnings[0].replace(/。$/, ""));
  else if (midConfidence) reasons.push("没有识别出数学结构，上面的结果可能有误");
  const action = aiUnavailable ? "请稍后在 AI 服务可用时再试，或联系开发者反馈。" : "建议选「用 AI 重新转译」按钮核对结果。";
  $("transcribe-fallback-reason").textContent = `${reasons.join("；")}。${action}`;
}

async function startTranscription(text, sourceNote, options) {
  const t = (text || "").trim();
  if (!t) {
    setStatus("没有可转译的内容。请先选中公式按 Ctrl+Shift+M，或在「开始」区粘贴内容后按「转译粘贴的公式」。", "error");
    return;
  }
  // 新转译开始：收起讲解/追问与上一条转译结果，避免新旧内容混淆
  $("result-section").hidden = true;
  $("ask-section").hidden = true;
  $("transcribe-section").hidden = true;
  $("confirm-box").hidden = true;
  $("candidates").hidden = true;
  const profile = currentTranscribeProfile();
  const profileName = profile === "spoken_structured" ? "结构朗读" : "紧凑文本";
  const engine = options && options.engine;
  const retryLabel = engine === "llm" ? "AI 重新转译" : "转译";
  setStatus(`正在${retryLabel}（${sourceNote}，${profileName}）：把读屏读不了的符号转成可读纯文本，不解释…`);
  try {
    const body = { text: t, source_type: "selection", profile };
    if (engine) body.engine = engine;
    const data = await apiPost("/api/transcribe-symbols", body);
    if (!data.ok || !data.transcribed_text) {
      setStatus(`转译失败：${data.error || "未知错误"}。可再试一次；若仍不行，可在「开始」区直接粘贴 LaTeX。`, "error");
      return;
    }
    lastTranscription = {
      original: t,
      result: data.transcribed_text,
      sourceNote,
      profile,
      confidence: data.confidence,
      warnings: data.warnings || [],
      residue: data.residue || [],
      source: data.source || "",
    };
    $("transcribe-slot").textContent = data.transcribed_text;
    renderTranscribeWarnings(data.warnings);
    renderTranscribeFallback(data);
    $("transcribe-section").hidden = false;
    // 转译结果自动入历史（与讲解一致，不需用户额外点保存）
    await addTranscriptionHistory(t, data.transcribed_text);
    const conf = data.confidence === "high" ? "置信度：高。"
      : data.confidence === "medium" ? "置信度：中，请核对后再使用。"
      : "置信度：低，请重点核对。";
    const tip = data.warnings && data.warnings.length ? `有 ${data.warnings.length} 条提醒，请核对。` : "";
    // 结果文本直接进 aria-live 播报：读屏用户不用自己去找结果区
    const resultSpeech = `转译结果：${data.transcribed_text}。`;
    if (!$("transcribe-fallback").hidden) {
      const aiRetryDisabled = $("transcribe-ai-retry-btn").disabled;
      const focusTarget = aiRetryDisabled ? "transcribe-edit-source-btn" : "transcribe-ai-retry-btn";
      const focusText = aiRetryDisabled ? "手动修改或粘贴" : "用 AI 重新转译";
      setStatus(`转译完成。${conf}${tip}${resultSpeech}${aiRetryDisabled ? "AI 重新转译当前不可用，" : ""}可手动修改原文。焦点在「${focusText}」按钮。`);
      $(focusTarget).focus();
    } else {
      setStatus(`转译完成。${conf}${tip}${resultSpeech}焦点在「复制转译结果」按钮，按回车复制；也可进一步讲解这个公式。`);
      $("transcribe-copy-btn").focus();
    }
  } catch (e) {
    announceBackendDown(e);
  }
}

function transcribeToExplain() {
  if (!lastTranscription) return;
  // 转译结果保留在屏上，讲解作为增量结果叠加；避免几十秒等待期白屏
  setStatus("正在提交讲解请求。讲解要调用大模型，通常需要 10 到 40 秒；转译结果保留在下方，可随时查看。想放弃可按 Esc 或「取消本次分析」。");
  explainIncomingText(lastTranscription.original, "转译结果进一步讲解");
}

// 换朗读风格：听完结果再决定换才符合直觉；切换后立即重转并播报后果
async function toggleTranscribeProfile() {
  if (!lastTranscription) return;
  const next = currentTranscribeProfile() === "spoken_structured" ? "unicode_compact" : "spoken_structured";
  try { localStorage.setItem(PROFILE_KEY, next); } catch (e) { /* 忽略 */ }
  setStatus(`已切换为${profileName(next)}风格，正在重新转译…`);
  await startTranscription(lastTranscription.original, lastTranscription.sourceNote || "当前公式");
  setStatus(`已按${profileName(next)}重新转译。如不习惯，可再按「换朗读风格」切回。`);
  $("transcribe-copy-btn").focus();
}

function retryTranscriptionWithAi() {
  if (!lastTranscription) return;
  startTranscription(lastTranscription.original, "AI 重新转译", { engine: "llm" });
}

function editTranscriptionSource() {
  if (!lastTranscription) return;
  focusTextInput("原文已放入手动粘贴框。你可以修改后重新转译。");
  $("paste-input").value = lastTranscription.original;
  $("paste-input").focus();
}

// analyzeLatex：拿到可信 LaTeX 后直接开讲（高置信度路径不经过确认框）
async function analyzeLatex(latex, sourceNote, note) {
  if (!latex) {
    setStatus("公式为空。请先选中公式按 Ctrl+Shift+M，或在「开始」区粘贴内容。", "error");
    return;
  }
  // 不再隐藏候选列表：从提取列表点进来的用户要保留「读法 + LaTeX + 附近正文」
  // 路标，听完一条还能换另一条；非候选入口（粘贴/确认）进来时列表本就隐藏
  $("confirm-box").hidden = true;
  setAnalyzing(true);
  const listKept = !$("candidates").hidden;
  setStatus(`已识别公式（${sourceNote}），正在讲解，通常需要 20 秒左右。可按「取消本次分析」停止等待。` +
    (listKept ? "公式列表仍保留在上方，可随时选择其他公式。" : ""));
  abortCtrl = new AbortController();
  try {
    const data = await apiPost(
      "/api/parse-latex",
      { latex, with_explanation: true, fraction_style: currentFractionStyle(), context: pendingContext || undefined },
      abortCtrl.signal
    );
    if (!data.ok) {
      setStatus(`讲解失败：${data.error || "未知错误"}。请检查公式后重试。`, "error");
      return;
    }
    currentLatex = latex;
    currentData = data;
    renderResult(data);
    await addHistory(latex, data);
    const exp = data.explanation || {};
    const name = exp.formula_name || "公式";
    // 20 秒等待的第一句播报就给出核心结论，不让用户再自己爬去找
    const firstSent = ((exp.accessible_summary || "").split(/[。！？]/)[0] || "").trim();
    const warnCount = (exp.consistency_warnings || []).length;
    const warnNote = warnCount ? `注意，有 ${warnCount} 条可靠性提醒，已列在讲解开头。` : "";
    $("result-heading").focus();
    if (explainVoiceMode() === "tts") {
      // AI 语音模式：状态只留一句短提示，语音合成完自动播，避免和读屏双声道重叠
      setStatus(`讲解完成：${name}。${warnNote}AI 语音即将朗读结构读法与摘要。`);
      playAiExplanation();
    } else {
      setStatus(`讲解完成：${name}。${firstSent ? firstSent + "。" : ""}${warnNote}短讲解已显示，可继续追问。`);
    }
  } catch (e) {
    if (e.name === "AbortError") {
      setStatus("本次讲解已取消。");
    } else {
      announceBackendDown(e);
    }
  } finally {
    setAnalyzing(false);
    abortCtrl = null;
  }
}

// 确认框的「确认并讲解」：以用户编辑后的内容为准
async function analyze() {
  await analyzeLatex($("confirm-input").value.trim(), "用户确认结果", "");
}

function renderResult(data) {
  stopAiSpeak(); // 新结果上来，停掉上一条公式的 AI 语音
  $("transcribe-section").hidden = true; // 讲解结果与转译结果不同时展示
  const exp = data.explanation || {};
  const confMap = { high: ["高", "conf-high"], medium: ["中", "conf-medium"], low: ["低（根据结构推断）", "conf-low"] };
  const [confText, confClass] = confMap[exp.confidence] || ["未知", "conf-medium"];

  const nameSlot = $("name-slot");
  nameSlot.textContent = "";
  nameSlot.append(exp.formula_name || "未命名公式");
  if (exp.domain) nameSlot.append(` · ${exp.domain}`);
  const badge = document.createElement("span");
  badge.className = `badge ${confClass}`;
  badge.textContent = `置信度：${confText}`;
  nameSlot.append(badge);

  $("summary-slot").textContent = exp.accessible_summary || exp.overview || "";

  // 可靠性提醒：机器交叉校验发现讲解与公式结构不一致时，明确告知用户别全信
  const wslot = $("warnings-slot");
  const warns = exp.consistency_warnings || [];
  wslot.innerHTML = "";
  if (warns.length) {
    const title = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = "可靠性提醒：";
    title.appendChild(strong);
    wslot.appendChild(title);
    warns.forEach((w) => {
      const p = document.createElement("p");
      p.textContent = w;
      wslot.appendChild(p);
    });
    wslot.hidden = false;
  } else {
    wslot.hidden = true;
  }

  $("purpose-slot").textContent = exp.purpose || "";
  $("intuition-slot").textContent = exp.intuition || "";

  // 变量真表格
  const vars = exp.variables || [];
  const vslot = $("variables-slot");
  vslot.innerHTML = "";
  if (vars.length) {
    const table = document.createElement("table");
    table.innerHTML = "<thead><tr><th>符号</th><th>角色</th><th>含义</th></tr></thead>";
    const tbody = document.createElement("tbody");
    vars.forEach((v) => {
      const tr = document.createElement("tr");
      [v.symbol, v.role, v.meaning].forEach((t) => {
        const td = document.createElement("td");
        td.textContent = t || "";
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    vslot.appendChild(table);
  } else {
    vslot.innerHTML = '<p class="hint">无变量说明。</p>';
  }

  $("speech-slot").textContent = data.speech_text || "";
  const cslot = $("concept-slot");
  cslot.innerHTML = "";
  (exp.concept_layers || []).forEach((layer, i) => {
    const h = document.createElement("p");
    const strong = document.createElement("strong");
    strong.textContent = `${i + 1}. ${layer.title || ""}`;
    h.appendChild(strong);
    h.append(` ${layer.content || ""}`);
    cslot.appendChild(h);
  });
  const mslot = $("misunderstanding-slot");
  mslot.innerHTML = "";
  (exp.common_misunderstandings || []).forEach((m) => {
    const li = document.createElement("li");
    li.textContent = m;
    mslot.appendChild(li);
  });
  $("latex-slot").textContent = data.latex;
  $("open-web-link").href = `${apiBase()}/?latex=${encodeURIComponent(data.latex)}`;

  // 推荐问题
  const qslot = $("suggested-questions");
  qslot.innerHTML = "";
  (exp.suggested_questions || []).slice(0, 3).forEach((q) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "secondary";
    btn.textContent = q;
    btn.setAttribute("aria-label", `使用推荐问题：${q}`);
    btn.addEventListener("click", () => {
      $("ask-input").value = q;
      $("ask-input").focus();
    });
    qslot.appendChild(btn);
  });

  $("detail-fold").open = false;
  $("result-section").hidden = false;
  $("ask-section").hidden = false;
}

// ---------------- 复制 ----------------

function shortText() {
  const exp = (currentData && currentData.explanation) || {};
  return [
    `【公式】${exp.formula_name || ""}`,
    `【一段话总结】${exp.accessible_summary || ""}`,
    `【用途】${exp.purpose || ""}`,
    `【直觉】${exp.intuition || ""}`,
    ...(exp.variables || []).map((v) => `- ${v.symbol}（${v.role}）：${v.meaning}`),
  ].join("\n");
}

// ---------------- 追问 ----------------

async function askQuestion() {
  const q = $("ask-input").value.trim();
  if (!q) {
    setStatus("请先输入问题。", "error");
    return;
  }
  if (!currentLatex) {
    setStatus("请先分析一条公式，再追问。", "error");
    return;
  }
  $("ask-btn").disabled = true;
  // 焦点若停在刚禁用的「发送追问」上会听到「不可用」；移到状态区听「正在生成」
  if (document.activeElement === $("ask-btn")) {
    setStatus("正在提交问题，生成回答…");
    focusStatus();
  }
  const slot = $("answer-slot");
  slot.hidden = false;
  slot.textContent = "正在生成回答…";
  try {
    const data = await apiPost("/api/ask", { latex: currentLatex, question: q });
    slot.textContent = data.ok !== false && data.answer ? `回答：${data.answer}` : `回答失败：${data.error || "未知错误"}`;
  } catch (e) {
    slot.textContent = backendDownMsg(e);
  } finally {
    $("ask-btn").disabled = false;
  }
}

// ---------------- 历史（chrome.storage.local，20 条） ----------------

async function loadHistory() {
  const obj = await chrome.storage.local.get(HISTORY_KEY);
  return obj[HISTORY_KEY] || [];
}

async function addHistory(latex, data) {
  const exp = data.explanation || {};
  let items = await loadHistory();
  items = items.filter((it) => it.type !== "transcription" && it.latex !== latex);
  items.unshift({
    type: "explanation",
    time: new Date().toLocaleString("zh-CN"),
    latex,
    name: exp.formula_name || "未命名公式",
    summary: exp.accessible_summary || "",
  });
  items = items.slice(0, 20);
  await chrome.storage.local.set({ [HISTORY_KEY]: items });
  renderHistory(items);
}

// 转译历史：存完整原文与完整结果，同一原文只留最新一条，展示时截取（原文前 80 字 / 结果前 120 字）
async function addTranscriptionHistory(original, result) {
  let items = await loadHistory();
  items = items.filter((it) => !(it.type === "transcription" && it.original === original));
  items.unshift({
    type: "transcription",
    time: new Date().toLocaleString("zh-CN"),
    original,
    result,
  });
  items = items.slice(0, 20);
  await chrome.storage.local.set({ [HISTORY_KEY]: items });
  renderHistory(items);
}

function renderHistory(items) {
  const slot = $("history-slot");
  $("history-summary").textContent = `历史记录（${items.length} 条）`;
  $("history-clear-btn").hidden = items.length === 0;
  slot.innerHTML = "";
  if (!items.length) {
    slot.innerHTML = '<p class="hint">暂无记录。</p>';
    return;
  }
  const table = document.createElement("table");
  table.innerHTML = "<thead><tr><th>时间</th><th>类型</th><th>内容</th><th>操作</th></tr></thead>";
  const tbody = document.createElement("tbody");
  items.forEach((it) => {
    const tr = document.createElement("tr");
    const tdTime = document.createElement("td");
    tdTime.textContent = it.time;
    const tdType = document.createElement("td");
    const isTranscribe = it.type === "transcription";
    tdType.textContent = isTranscribe ? "转译" : "理解";
    const tdContent = document.createElement("td");
    const tdOps = document.createElement("td");
    const loadBtn = document.createElement("button");
    loadBtn.type = "button";
    loadBtn.className = "secondary";
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "secondary";
    if (isTranscribe) {
      const origPrev = (it.original || "").slice(0, 80);
      const resultPrev = (it.result || "").slice(0, 120);
      tdContent.textContent = `原文：${origPrev}${(it.original || "").length > 80 ? "…" : ""}`;
      loadBtn.textContent = "载入";
      loadBtn.setAttribute("aria-label", `重新载入转译结果：原文 ${origPrev.slice(0, 40)}`);
      loadBtn.addEventListener("click", () => {
        lastTranscription = { original: it.original, result: it.result };
        $("transcribe-slot").textContent = it.result;
        renderTranscribeWarnings([]);
        renderTranscribeFallback({ source: "history", confidence: "high", warnings: [], residue: [] });
        $("result-section").hidden = true;
        $("ask-section").hidden = true;
        $("transcribe-section").hidden = false;
        setStatus("已从历史载入转译结果，可复制或进一步讲解这个公式。");
        $("transcribe-copy-btn").focus();
      });
      copyBtn.textContent = "复制结果";
      copyBtn.setAttribute("aria-label", `复制转译结果：${resultPrev.slice(0, 40)}`);
      copyBtn.addEventListener("click", () => copyText(it.result, "转译结果"));
    } else {
      tdContent.textContent = it.name || "公式";
      loadBtn.textContent = "载入";
      loadBtn.setAttribute("aria-label", `重新载入：${it.name}`);
      loadBtn.addEventListener("click", () => {
        pendingContext = "";
        // 历史里是已分析过的可信 LaTeX：不再弹确认，直接重新讲解
        analyzeLatex(it.latex, "历史记录", "");
      });
      copyBtn.textContent = "复制总结";
      copyBtn.setAttribute("aria-label", `复制总结：${it.name}`);
      copyBtn.addEventListener("click", () => copyText(`${it.name}：${it.summary}`, "总结"));
    }
    tdOps.append(loadBtn, copyBtn);
    tr.append(tdTime, tdType, tdContent, tdOps);
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  slot.appendChild(table);
}

async function handleShortcutAction(action) {
  if (!action) return;
  if (action.kind === "open_setup") {
    await showShortcutSetup("首次使用 Ctrl+Shift+M，请先选择默认行为。");
    return;
  }

  const prefs = await loadShortcutPrefs();
  applyShortcutPrefsToState(prefs);
  hideShortcutSetup();

  if (action.kind === "shortcut_explain_scan") {
    setStatus("已按快捷键开始扫描并讲解本页公式。");
    extractPage();
    return;
  }

  if (action.kind === "shortcut_selection") {
    startTranscription(action.text || "", "快捷键选中内容");
    return;
  }

  if (action.kind === "shortcut_empty_selection") {
    focusTextInput("没有检测到选中内容。请先选中公式或题目区域后再按快捷键；也可以在此处粘贴文本后开始转译。", "error");
    return;
  }

  if (action.kind === "shortcut_text_input") {
    focusTextInput("已按文本输入模式打开。请粘贴题目、公式或化学式，然后按 Tab 到「开始转译」。");
    return;
  }

  if (action.kind === "shortcut_restricted_page") {
    focusTextInput("当前页面无法读取选中内容，可能是浏览器内置页面或受限页面。请复制内容后在此处手动粘贴。", "error");
  }
}

// ---------------- 事件绑定与初始化 ----------------

$("extract-btn").addEventListener("click", extractPage);
$("primary-action-btn").addEventListener("click", runPrimaryAction);
$("shortcut-save-btn").addEventListener("click", async () => {
  const prefs = {
    setupDone: $("shortcut-remember").checked,
    shortcutMode: radioValue("shortcut-mode", "selection_transcribe"),
    transcribeProfile: radioValue("shortcut-profile", "spoken_structured"),
  };
  await saveShortcutPrefs(prefs);
  applyShortcutPrefsToState(prefs);
  updateQuickStart(prefs);
  if (prefs.setupDone) {
    hideShortcutSetup();
    setStatus("快捷键默认行为已保存。以后按 Ctrl+Shift+M 会直接执行所选模式。");
  } else {
    hideShortcutSetup();
    setStatus("快捷键设置已临时应用。因为没有勾选保存，下次按 Ctrl+Shift+M 仍会先显示此设置。");
  }
});
$("shortcut-cancel-btn").addEventListener("click", () => {
  hideShortcutSetup();
  setStatus("已暂不设置快捷键默认行为。你仍可使用页面上的按钮。");
});
$("shortcut-edit-btn").addEventListener("click", () =>
  showShortcutSetup("正在修改 Ctrl+Shift+M 的默认行为。")
);
$("paste-btn").addEventListener("click", () => {
  pendingContext = "";
  handleIncomingText($("paste-input").value, "手动粘贴");
});
$("paste-explain-btn").addEventListener("click", () => {
  pendingContext = "";
  explainIncomingText($("paste-input").value, "手动粘贴");
});
$("transcribe-copy-btn").addEventListener("click", () =>
  copyText((lastTranscription && lastTranscription.result) || "", "转译结果")
);
$("profile-toggle-btn").addEventListener("click", toggleTranscribeProfile);
$("transcribe-to-explain-btn").addEventListener("click", transcribeToExplain);
$("transcribe-ai-retry-btn").addEventListener("click", retryTranscriptionWithAi);
$("transcribe-edit-source-btn").addEventListener("click", editTranscriptionSource);
$("confirm-btn").addEventListener("click", analyze);
$("reextract-btn").addEventListener("click", () => {
  $("confirm-box").hidden = true;
  $("confirm-input").value = "";
  setStatus("已清除。可重新选中公式后按主按钮，或点「自动提取页面所有公式」。");
  $("extract-btn").focus();
});
$("copy-only-btn").addEventListener("click", () =>
  copyText($("confirm-input").value.trim(), "识别结果")
);
$("cancel-btn").addEventListener("click", () => abortCtrl && abortCtrl.abort());
$("copy-short-btn").addEventListener("click", () => copyText(shortText(), "短讲解"));
$("copy-latex-btn").addEventListener("click", () => copyText(currentLatex, "LaTeX"));
$("copy-all-btn").addEventListener("click", () =>
  copyText((currentData && currentData.plain_text) || shortText(), "全部讲解")
);

// ---------------- AI 语音讲解（百炼 TTS）----------------
// 默认只在用户点击时播放（读屏用户不点它就完全无感）；
// 若用户在「服务设置」选了「自动播放 AI 语音」，讲解完成后自动播。
// 铁律：任何时刻只有一路声音——自动播放前会先停掉旧音频。
let aiAudio = null;
let aiAudioUrl = null;
// 「听 AI 讲解」的初始 aria-label：恢复默认态时还原，避免忙碌文案残留
const AI_SPEAK_ARIA = "用 AI 语音朗读公式朗读与一段话总结，再按一次停止";
function restoreAiSpeakBtn() {
  const btn = $("ai-speak-btn");
  btn.textContent = "听 AI 讲解";
  btn.setAttribute("aria-label", AI_SPEAK_ARIA);
  btn.disabled = false;
}
function stopAiSpeak() {
  if (aiAudio) { aiAudio.pause(); aiAudio = null; }
  if (aiAudioUrl) { URL.revokeObjectURL(aiAudioUrl); aiAudioUrl = null; }
  restoreAiSpeakBtn();
}
async function playAiExplanation() {
  if (!currentData) return;
  stopAiSpeak(); // 保证不会叠两路声音
  const exp = currentData.explanation || {};
  const text = [currentData.speech_text, exp.accessible_summary].filter(Boolean).join("。");
  const btn = $("ai-speak-btn");
  // 忙碌态：文案与读屏名称同步换成「生成音频中」，焦点移到状态区听完整提示
  enterBusyState(btn, "生成音频中", "正在生成音频，按钮暂时不可用，请稍候。");
  try {
    const resp = await fetch(`${apiBase()}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      restoreAiSpeakBtn();
      setStatus(`${err.error || "语音合成失败。"}请再按一次「听 AI 讲解」重试。`, "error");
      return;
    }
    aiAudioUrl = URL.createObjectURL(await resp.blob());
    aiAudio = new Audio(aiAudioUrl);
    aiAudio.onended = () => { stopAiSpeak(); setStatus("AI 讲解播放完毕。"); };
    await aiAudio.play();
    btn.textContent = "停止 AI 讲解";
    btn.setAttribute("aria-label", "停止 AI 讲解");
    setStatus("正在播放 AI 语音讲解，再按一次可停止。");
  } catch (e) {
    restoreAiSpeakBtn();
    setStatus(`语音合成请求出错：${e.message || e}。请检查网络后再按「听 AI 讲解」重试。`, "error");
  } finally {
    btn.disabled = false;
  }
}
$("ai-speak-btn").addEventListener("click", async () => {
  if (!currentData) return;
  if (aiAudio) { stopAiSpeak(); setStatus("已停止 AI 讲解。"); return; }
  await playAiExplanation();
});

// ---------------- 讲解朗读方式（sr = 屏幕阅读器 / tts = 自动 AI 语音）----------------
function explainVoiceMode() {
  try { return localStorage.getItem(EXPLAIN_VOICE_KEY) || "sr"; } catch (e) { return "sr"; }
}
document.querySelectorAll('input[name="explain-voice"]').forEach((r) =>
  r.addEventListener("change", () => {
    const v = radioValue("explain-voice", "sr");
    try { localStorage.setItem(EXPLAIN_VOICE_KEY, v); } catch (e) { /* 忽略 */ }
    if (v === "tts") {
      setStatus("已切换为自动 AI 语音：讲解完成后自动朗读结构读法与摘要。想中途停下按「停止 AI 讲解」。");
    } else {
      setStatus("已切换为屏幕阅读器直接读：插件不再自动播音，讲解文字由 NVDA 等读屏朗读。");
    }
  })
);
// 分式读法偏好：切换只影响下一次讲解（重讲要再花几十秒大模型调用，不自动重讲）
document.querySelectorAll('input[name="fraction-style"]').forEach((r) =>
  r.addEventListener("change", () => {
    const v = radioValue("fraction-style", "structured");
    try { localStorage.setItem(FRACTION_STYLE_KEY, v); } catch (e) { /* 忽略 */ }
    if (v === "compact") {
      setStatus("已切换为紧凑分式读法：分式读作「分母 分之 分子」。对下一次讲解生效，已显示的结果不变。");
    } else {
      setStatus("已切换为结构分式读法：分式读作「分数，分子是…分母是…，分数结束」。对下一次讲解生效，已显示的结果不变。");
    }
  })
);
$("ask-btn").addEventListener("click", askQuestion);
$("ask-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter") askQuestion();
});
// 编辑框内 Ctrl+回车 = 确认并分析（不离手完成主流程）
$("confirm-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    analyze();
  }
});
// 全局按键：Esc 取消分析/收起候选；数字键直选候选
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (abortCtrl) {
      abortCtrl.abort();
    } else if (!$("candidates").hidden) {
      $("candidates").hidden = true;
      setStatus("已收起候选列表。可重新提取、选中或粘贴公式。");
      $("extract-btn").focus();
    }
    return;
  }
  // 数字键直选（候选列表可见且焦点不在输入框时）
  if ($("candidates").hidden) return;
  const tag = (document.activeElement || {}).tagName;
  if (tag === "TEXTAREA" || tag === "INPUT") return;
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= candidateItems.length) {
    e.preventDefault();
    routeCandidate(candidateItems[n - 1]);
  }
});
$("history-clear-btn").addEventListener("click", async () => {
  if (!confirm("确定清空全部历史记录吗？此操作不可撤销。")) return;
  await chrome.storage.local.set({ [HISTORY_KEY]: [] });
  renderHistory([]);
  setStatus("历史记录已清空。");
});

// 服务地址设置：保存 + 测试连接
$("api-base-save-btn").addEventListener("click", async () => {
  const v = $("api-base-input").value.trim().replace(/\/+$/, "");
  try {
    if (v) localStorage.setItem(API_KEY, v);
    else localStorage.removeItem(API_KEY);
  } catch (e) { /* 忽略 */ }
  setStatus("正在测试连接…");
  try {
    const resp = await fetch(apiBase() + "/api/health", { headers: authHeaders() });
    if (!resp.ok) throw new Error();
    setStatus(`已保存并连接成功：${apiBase()}`);
  } catch (e) {
    setStatus(`已保存，但连不上 ${apiBase()}。请确认服务已启动；或按上方「恢复默认云端服务」一键还原。`, "error");
    $("cloud-reset-btn").hidden = false;
  }
});

// 连接失败时的一键自救：清掉自定义地址回到默认云端并当场测连，
// 免得读屏用户摸进「服务设置」手动清空地址
$("cloud-reset-btn").addEventListener("click", async () => {
  try { localStorage.removeItem(API_KEY); } catch (e) { /* 忽略 */ }
  $("api-base-input").value = DEFAULT_API;
  setStatus("已恢复默认云端地址，正在测试连接…");
  try {
    const resp = await fetch(apiBase() + "/api/health", { headers: authHeaders() });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    setStatus(`连接成功：已恢复云端服务。可以重试刚才的操作了。`);
  } catch (e) {
    setStatus(`云端服务暂时也连不上（${DEFAULT_API}）。可能是临时波动，请过几分钟再试；仍不行请联系开发者。`, "error");
  }
});

// 自愈授权：点击后调起浏览器授权对话框（可选权限，仅在注入失败且用户主动按下时申请）。
// 授权成功后自动重试刚才失败的动作；拒绝则回退到工具栏图标授权/粘贴的指引。
$("auth-grant-btn").addEventListener("click", async () => {
  const btn = $("auth-grant-btn");
  btn.disabled = true;
  setStatus("正在请求授权。浏览器会弹出授权对话框，询问是否允许插件读取和更改网站数据：请按读屏提示在对话框里按「允许」。授权一次后永久生效。");
  let granted = false;
  try {
    granted = await chrome.permissions.request({ origins: ["<all_urls>"] });
  } catch (e) {
    btn.disabled = false;
    setStatus(`授权请求失败：${e.message || e}。请改用工具栏插件图标在页面上点一下授权，或直接粘贴内容。`, "error");
    btn.hidden = false; // setStatus 内部会隐藏按钮，失败时重新亮出来供再次尝试
    btn.focus();
    return;
  }
  btn.hidden = true;
  btn.disabled = false;
  if (granted) {
    setStatus("授权成功，正在重试刚才的操作。");
    const fn = pendingRetry;
    pendingRetry = null;
    if (fn) fn();
  } else {
    setStatus("未获得授权。您可以先点一下浏览器工具栏上的插件图标（授权当前页面），再按一次刚才的按钮；也可以直接粘贴内容。", "error");
  }
});

$("diag-run-btn").addEventListener("click", () => { runDiagnosis(); });
$("diag-copy-btn").addEventListener("click", async () => {
  await copyText($("diag-output").value, "诊断信息");
});

// ---------------- 问题诊断（远程支持用：生成可复制的纯文本诊断报告）----------------
async function runDiagnosis() {
  setStatus("正在运行诊断，请稍候…");
  const lines = [];
  lines.push("数学公式无障碍学习助手 诊断信息");
  lines.push("时间：" + new Date().toLocaleString());
  lines.push("插件版本：" + chrome.runtime.getManifest().version);
  lines.push("浏览器：" + navigator.userAgent);
  let tab;
  try { [tab] = await chrome.tabs.query({ active: true, currentWindow: true }); } catch (e) { /* 忽略 */ }
  lines.push("当前页面地址：" + ((tab && tab.url) || "(未知)"));
  lines.push("当前页面标题：" + ((tab && tab.title) || "(未知)"));
  let inject = "未测试";
  if (tab) {
    try {
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => true });
      inject = "注入成功（页面可被插件访问）";
    } catch (e) {
      inject = "注入失败：" + classifyInjectError(e && e.message, tab.url)
        + " | 原始错误：" + (e && e.message || "无");
    }
  }
  lines.push("页面注入测试：" + inject);
  lines.push("服务地址：" + apiBase() + (apiBase() === DEFAULT_API ? "（默认云端）" : "（自定义）"));
  let health = "未测试";
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 10000);
    const resp = await fetch(apiBase() + "/api/health", { headers: authHeaders(), signal: ctrl.signal });
    clearTimeout(timer);
    if (!resp.ok) {
      health = `HTTP ${resp.status}`;
    } else {
      health = `连接正常（HTTP ${resp.status}`;
      try {
        const d = await resp.json();
        if (d && d.llm) health += "，大模型可用=" + d.llm.available;
      } catch (e) { /* 忽略 */ }
      health += "）";
    }
  } catch (e) {
    health = "连接失败：" + (e && e.message || "无详情");
  }
  lines.push("服务连接：" + health);
  lines.push("转译风格：" + profileName(currentTranscribeProfile()));
  lines.push("讲解朗读方式：" + (explainVoiceMode() === "tts" ? "自动 AI 语音" : "屏幕阅读器直接读"));
  const report = lines.join("\n");
  $("diag-output").value = report;
  $("diag-box").hidden = false;
  setStatus("诊断完成，结果已放入只读文本框。按 Tab 到「复制诊断信息」按钮，把结果发给开发者即可。");
  $("diag-copy-btn").focus();
}

// 右键菜单 / 快捷键送来的捕获内容
chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "capture" && msg.payload) {
    chrome.storage.session.remove("pendingCapture");
    pendingContext = "";
    handleIncomingText(msg.payload.text, "页面选中内容");
  } else if (msg && msg.type === "shortcut-action" && msg.action) {
    chrome.storage.session.remove("pendingShortcutAction");
    handleShortcutAction(msg.action);
  }
});

(async function init() {
  const prefs = await loadShortcutPrefs();
  updateQuickStart(prefs);
  applyShortcutPrefsToState(prefs);
  // 练习页链接随服务地址变化（云端/本机都能打开）
  $("practice-link").href = `${apiBase()}/static/plugin_test_page.html`;
  try { $("api-base-input").value = localStorage.getItem(API_KEY) || DEFAULT_API; } catch (e) { /* 忽略 */ }
  const evMode = explainVoiceMode();
  document.querySelectorAll('input[name="explain-voice"]').forEach((r) => { r.checked = r.value === evMode; });
  const fsMode = currentFractionStyle();
  document.querySelectorAll('input[name="fraction-style"]').forEach((r) => { r.checked = r.value === fsMode; });
  renderHistory(await loadHistory());
  // 面板打开前触发的捕获（右键/快捷键先于面板加载）
  const obj = await chrome.storage.session.get("pendingCapture");
  if (obj.pendingCapture) {
    await chrome.storage.session.remove("pendingCapture");
    pendingContext = "";
    handleIncomingText(obj.pendingCapture.text, "页面选中内容");
  }
  const actionObj = await chrome.storage.session.get("pendingShortcutAction");
  if (actionObj.pendingShortcutAction) {
    await chrome.storage.session.remove("pendingShortcutAction");
    await handleShortcutAction(actionObj.pendingShortcutAction);
  }
  // 后端健康提示（不阻塞）
  try {
    const resp = await fetch(apiBase() + "/api/health", { headers: authHeaders() });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  } catch (e) {
    announceBackendDown(e, false); // 开面板健康检查：只显恢复按钮，不抢焦点
  }
})();
