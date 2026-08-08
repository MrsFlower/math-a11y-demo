// 侧边面板逻辑：捕获 → 确认 → 分析 → 追问 → 历史。
// 状态机：空闲 idle / 捕获中 capturing / 识别待确认 confirm / 分析中 analyzing / 已完成 done / 失败可重试 error
// 所有状态变化都写入 #status（aria-live），读屏自动播报。

// 默认连云端（百炼高代码应用 FC 触发器），用户开箱即用；
// 也可在底部「服务设置」改回本机 http://127.0.0.1:8321
const DEFAULT_API = "https://highcodpmiufnwj-cvgvqsopuz.cn-beijing.fcapp.run";
// FC 触发器鉴权 token（无 Authorization 头会被网关拒绝）；对本地服务附带无副作用
const DEFAULT_TOKEN = "6973c90b-ce3b-45c1-8c0b-7897f1797106";
const API_KEY = "math_a11y_api_base_v1";
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

// ---------------- 状态与工具 ----------------

function setStatus(msg, kind) {
  const el = $("status");
  el.textContent = msg;
  if (kind === "error") el.dataset.kind = "error";
  else delete el.dataset.kind;
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
    setStatus(`复制失败：${e.message}`, "error");
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
  return `无法连接理解服务（${apiBase()}）${reason}。请检查网络连接；或在底部「服务设置」里换一个可用的服务地址（本机服务为 http://127.0.0.1:8321）。`;
}

// ---------------- 工作模式（第五阶段：转译为主，理解为辅） ----------------
// 转译模式：把读屏读不了的理科符号转成可读纯文本，不解释、不客套。
// 理解模式：原有确认 -> 分析 -> 追问流程，完全保留。

function currentMode() {
  const el = document.querySelector('input[name="work-mode"]:checked');
  return el ? el.value : "transcribe";
}

function currentTranscribeProfile() {
  const el = document.querySelector('input[name="transcribe-profile"]:checked');
  return el ? el.value : "spoken_structured";
}

function radioValue(name, fallback) {
  const el = document.querySelector(`input[name="${name}"]:checked`);
  return el ? el.value : fallback;
}

function setRadioValue(name, value) {
  const el = document.querySelector(`input[name="${name}"][value="${value}"]`);
  if (el) el.checked = true;
}

function applyMode() {
  const transcribe = currentMode() === "transcribe";
  $("paste-btn").textContent = transcribe ? "开始转译" : "送入确认";
  $("transcribe-profile-box").hidden = !transcribe;
}

document.querySelectorAll('input[name="work-mode"]').forEach((r) =>
  r.addEventListener("change", applyMode)
);

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

function applyShortcutPrefsToWorkMode(prefs) {
  if (prefs.shortcutMode === "explain_scan") {
    setRadioValue("work-mode", "explain");
  } else {
    setRadioValue("work-mode", "transcribe");
    setRadioValue("transcribe-profile", prefs.transcribeProfile || "spoken_structured");
  }
  applyMode();
  updateQuickStart(prefs);
}

function shortcutModeLabel(prefs) {
  if (prefs.shortcutMode === "explain_scan") return "扫描当前页面公式并进入理解模式";
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
  setRadioValue("work-mode", "transcribe");
  applyMode();
  $("alternate-actions").open = true;
  $("paste-fold").open = true;
  $("confirm-box").hidden = true;
  $("candidates").hidden = true;
  $("transcribe-section").hidden = true;
  setStatus(message, kind);
  $("paste-input").focus();
}

async function runPrimaryAction() {
  const prefs = await loadShortcutPrefs();
  applyShortcutPrefsToWorkMode(prefs);
  hideShortcutSetup();
  if (prefs.shortcutMode === "explain_scan") {
    setStatus("正在按默认方式扫描当前页面公式。");
    extractPage();
    return;
  }
  if (prefs.shortcutMode === "text_input") {
    focusTextInput("请粘贴题目、公式或化学式，然后按 Tab 到「开始转译」。");
    return;
  }
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const [ret] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });
    const text = (ret && ret.result || "").trim();
    if (text) {
      startTranscription(text, "当前页面选中内容");
    } else {
      focusTextInput("没有检测到选中内容。请先选中公式或题目区域后再点主按钮；也可以在此处粘贴文本后开始转译。", "error");
    }
  } catch (e) {
    focusTextInput("当前页面无法读取选中内容，可能是浏览器内置页面或受限页面。请复制内容后在此处手动粘贴。", "error");
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
  setStatus(`${sourceNote}捕获成功，正在生成朗读预览。焦点已在「确认并分析」按钮，按回车开始分析；需修改请按 Shift+Tab 进入编辑框。`);
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

// 统一处理送入的文本（选中 / 粘贴 / 右键捕获）：按当前模式分流。
// 转译模式不要求用户拥有 LaTeX，直接转译原文；理解模式沿用原流程。
async function handleIncomingText(text, sourceNote) {
  $("extract-suggest").hidden = true;
  const t = (text || "").trim();
  if (!t) {
    setStatus("没有捕获到内容。请先在页面上选中内容，或改用手动粘贴。", "error");
    return;
  }
  if (currentMode() === "transcribe") {
    startTranscription(t, sourceNote);
    return;
  }
  if (looksLikeLatex(t)) {
    enterConfirm(t, sourceNote, "内容像 LaTeX 源码，已直接送入确认。");
    return;
  }
  setStatus("捕获到普通文本，正在转换为 LaTeX…");
  try {
    const data = await apiPost("/api/normalize-input", { text: t });
    if (data.ok && data.latex) {
      const conf = data.confidence === "high" ? "转换置信度：高。"
        : data.confidence === "medium" ? "转换置信度：中，请检查。"
        : "转换置信度：低，请仔细检查每个符号。";
      enterConfirm(data.latex, `${sourceNote}（已自动转换）`, conf + (data.notes ? ` ${data.notes}` : ""));
    } else {
      setStatus(`转换失败：${data.error || "未识别出公式"}。可在下方手动粘贴 LaTeX。`, "error");
    }
  } catch (e) {
    setStatus(backendDownMsg(e), "error");
  }
}

// 提取本页公式（注入 content.js）
async function extractPage() {
  if (currentMode() === "transcribe") {
    // 不报错劝退，直接给一步到位的按钮（焦点落在按钮上，读屏用户听完说明按回车即可）
    $("alternate-actions").open = true;
    $("extract-suggest").hidden = false;
    setStatus("提取公式属于理解模式（找出页面上的 LaTeX 并讲解）。焦点已在「切到理解模式并提取」按钮，按回车一步完成；若只想转译选中内容，请用「使用选中内容」。");
    $("extract-switch-btn").focus();
    return;
  }
  $("extract-suggest").hidden = true;
  setStatus("正在提取本页公式…");
  $("candidates").hidden = true;
  let results;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab) throw new Error("找不到当前标签页");
    [results] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content.js"],
    });
  } catch (e) {
    setStatus("此页面无法提取（浏览器内置页面或受限页面）。请改用选中发送或手动粘贴。", "error");
    return;
  }
  const found = (results && results.result) || [];
  if (found.length === 0) {
    $("alternate-actions").open = true;
    setStatus("当前页面没有检测到可识别的公式。请切换到包含公式的页面后再扫描；也可以先选中公式或题目区域，再点「使用选中内容」，或打开手动粘贴。焦点已在「使用选中内容」按钮。", "error");
    $("selection-btn").focus();
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
  setStatus(`找到 ${found.length} 个公式，已转成中文朗读。按数字键 1 到 ${Math.min(found.length, 9)} 直接选择，或用 Tab 浏览列表。`);
  $("candidates-heading").focus();
}

function routeCandidate(f) {
  pendingContext = f.context || ""; // 带上公式周围正文，帮后端判断符号含义
  if (f.kind === "latex") {
    enterConfirm(f.latex, f.source, "页面自带源码，识别零误差。");
  } else {
    handleIncomingText(f.latex, f.source);
  }
}

// 读取当前页选中内容
async function useSelection() {
  pendingContext = "";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const [ret] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });
    handleIncomingText(ret && ret.result, "当前页面选中内容");
  } catch (e) {
    setStatus("无法读取选中内容（受限页面）。请改用手动粘贴。", "error");
  }
}

// ---------------- 分析 ----------------

function setAnalyzing(on) {
  ["extract-btn", "selection-btn", "paste-btn", "confirm-btn", "reextract-btn",
   "transcribe-copy-btn", "transcribe-save-btn", "transcribe-to-explain-btn"].forEach(
    (id) => ($(id).disabled = on)
  );
  $("cancel-btn").hidden = !on;
}

// ---------------- 转译（第五阶段） ----------------

let lastTranscription = null; // { original, result }

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

async function startTranscription(text, sourceNote) {
  const t = (text || "").trim();
  if (!t) {
    setStatus("没有可转译的内容。", "error");
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
  setStatus(`正在转译（${sourceNote}，${profileName}）：把读屏读不了的符号转成可读纯文本，不解释…`);
  try {
    const data = await apiPost("/api/transcribe-symbols", { text: t, source_type: "selection", profile });
    if (!data.ok || !data.transcribed_text) {
      setStatus(`转译失败：${data.error || "未知错误"}`, "error");
      return;
    }
    lastTranscription = { original: t, result: data.transcribed_text };
    $("transcribe-slot").textContent = data.transcribed_text;
    renderTranscribeWarnings(data.warnings);
    $("transcribe-section").hidden = false;
    const conf = data.confidence === "high" ? "置信度：高。"
      : data.confidence === "medium" ? "置信度：中，请核对后再使用。"
      : "置信度：低，请重点核对。";
    const tip = data.warnings && data.warnings.length ? `有 ${data.warnings.length} 条提醒，请核对。` : "";
    setStatus(`转译完成。${conf}${tip}焦点在「复制转译结果」按钮，按回车复制；也可保存到历史或转去理解模式。`);
    $("transcribe-copy-btn").focus();
  } catch (e) {
    setStatus(backendDownMsg(e), "error");
  }
}

function saveTranscription() {
  if (!lastTranscription) return;
  addTranscriptionHistory(lastTranscription.original, lastTranscription.result);
  setStatus("已保存到历史记录。");
}

function transcribeToExplain() {
  if (!lastTranscription) return;
  const radio = document.querySelector('input[name="work-mode"][value="explain"]');
  radio.checked = true;
  radio.dispatchEvent(new Event("change"));
  $("transcribe-section").hidden = true;
  handleIncomingText(lastTranscription.original, "转译结果转理解");
}

async function analyze() {
  const latex = $("confirm-input").value.trim();
  if (!latex) {
    setStatus("公式为空，请先捕获或粘贴。", "error");
    return;
  }
  setAnalyzing(true);
  setStatus("正在分析，通常需要 20 秒左右。可按「取消本次分析」停止等待。");
  abortCtrl = new AbortController();
  try {
    const data = await apiPost(
      "/api/parse-latex",
      { latex, with_explanation: true, context: pendingContext || undefined },
      abortCtrl.signal
    );
    if (!data.ok) {
      setStatus(`分析失败：${data.error || "未知错误"}。请检查公式后重试。`, "error");
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
    setStatus(`分析完成：${name}。${firstSent ? firstSent + "。" : ""}${warnNote}短讲解已显示，可继续追问。`);
    $("result-heading").focus();
  } catch (e) {
    if (e.name === "AbortError") {
      setStatus("本次分析已取消。");
    } else {
      setStatus(backendDownMsg(e), "error");
    }
  } finally {
    setAnalyzing(false);
    abortCtrl = null;
  }
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

// 转译历史：存完整原文与完整结果，展示时截取（原文前 80 字 / 结果前 120 字）
async function addTranscriptionHistory(original, result) {
  let items = await loadHistory();
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
        $("result-section").hidden = true;
        $("ask-section").hidden = true;
        $("transcribe-section").hidden = false;
        setStatus("已从历史载入转译结果，可复制或转去理解模式。");
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
        enterConfirm(it.latex, "历史记录", "之前分析过，按「确认并分析」重新生成讲解。");
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
  applyShortcutPrefsToWorkMode(prefs);
  hideShortcutSetup();

  if (action.kind === "shortcut_explain_scan") {
    setStatus("已按快捷键进入理解模式，正在扫描当前页面公式。");
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
$("extract-switch-btn").addEventListener("click", () => {
  const r = document.querySelector('input[name="work-mode"][value="explain"]');
  r.checked = true;
  r.dispatchEvent(new Event("change"));
  extractPage();
});
$("primary-action-btn").addEventListener("click", runPrimaryAction);
$("selection-btn").addEventListener("click", useSelection);
$("shortcut-save-btn").addEventListener("click", async () => {
  const prefs = {
    setupDone: $("shortcut-remember").checked,
    shortcutMode: radioValue("shortcut-mode", "selection_transcribe"),
    transcribeProfile: radioValue("shortcut-profile", "spoken_structured"),
  };
  await saveShortcutPrefs(prefs);
  applyShortcutPrefsToWorkMode(prefs);
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
$("transcribe-copy-btn").addEventListener("click", () =>
  copyText((lastTranscription && lastTranscription.result) || "", "转译结果")
);
$("transcribe-save-btn").addEventListener("click", saveTranscription);
$("transcribe-to-explain-btn").addEventListener("click", transcribeToExplain);
$("confirm-btn").addEventListener("click", analyze);
$("reextract-btn").addEventListener("click", () => {
  $("confirm-box").hidden = true;
  $("confirm-input").value = "";
  setStatus("已清除。请重新提取、选中或粘贴公式。");
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
// 铁律：只在用户点击时播放，绝不自动，读屏用户不点它就完全无感。
// 服务低视力/未装读屏的用户与演示场景。
let aiAudio = null;
let aiAudioUrl = null;
function stopAiSpeak() {
  if (aiAudio) { aiAudio.pause(); aiAudio = null; }
  if (aiAudioUrl) { URL.revokeObjectURL(aiAudioUrl); aiAudioUrl = null; }
  $("ai-speak-btn").textContent = "听 AI 讲解";
}
$("ai-speak-btn").addEventListener("click", async () => {
  if (!currentData) return;
  if (aiAudio) { stopAiSpeak(); setStatus("已停止 AI 讲解。"); return; }
  const exp = currentData.explanation || {};
  const text = [currentData.speech_text, exp.accessible_summary].filter(Boolean).join("。");
  const btn = $("ai-speak-btn");
  btn.disabled = true;
  setStatus("正在合成语音，首次约需几秒…");
  try {
    const resp = await fetch(`${apiBase()}/api/tts`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      setStatus(err.error || "语音合成失败。", "error");
      return;
    }
    aiAudioUrl = URL.createObjectURL(await resp.blob());
    aiAudio = new Audio(aiAudioUrl);
    aiAudio.onended = () => { stopAiSpeak(); setStatus("AI 讲解播放完毕。"); };
    await aiAudio.play();
    btn.textContent = "停止 AI 讲解";
    setStatus("正在播放 AI 语音讲解，再按一次可停止。");
  } catch (e) {
    setStatus(`语音合成请求出错：${e.message || e}`, "error");
  } finally {
    btn.disabled = false;
  }
});
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
    setStatus(`已保存，但连不上 ${apiBase()}。请确认服务已启动，或改回默认地址。`, "error");
  }
});

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
  applyMode();
  const prefs = await loadShortcutPrefs();
  updateQuickStart(prefs);
  applyShortcutPrefsToWorkMode(prefs);
  try { $("api-base-input").value = localStorage.getItem(API_KEY) || DEFAULT_API; } catch (e) { /* 忽略 */ }
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
    setStatus(backendDownMsg(e), "error");
  }
})();
