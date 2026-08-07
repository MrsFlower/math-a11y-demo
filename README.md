# 数学公式无障碍学习助手（原型）

面向视障学生的理科学习无障碍 Agent 原型。本项目有两个模式：

- **转译模式**解决“读得出来”：把题目/讲义/化学式里读屏读不了的理科符号
  （根号、对数、上下标、化学式、离子、几何记号）转成可听、可复制、可保存的
  Unicode 纯文本——不解释、不客套、不解题，只转符号。
- **理解模式**解决“学得明白”：输入 LaTeX 公式（或上传公式图片），获得
  中文短讲解与分层详解，并可以继续追问。

先让理科符号可读，再在需要时帮助理解。输入 LaTeX 公式后，理解模式输出：

- 这是什么公式（公式名称 + 领域 + 置信度）与它「用来做什么」
- 不含符号的直觉解释（先讲思想，再讲结构）
- 变量角色表（每个符号的角色与含义）
- 结构层级 + 概念理解（两者分区展示，不混在一起）
- 中文可朗读文本（为读屏器优化的口语化表达）
- 常见误解、可继续追问的问题、一段话无障碍总结
- 层级结构树（每个子结构可单独「追问」）
- 纯文本无障碍版解释（一键复制）/ 原始 LaTeX / MathML
- 「听 AI 讲解」按钮（百炼 Qwen-TTS）：服务低视力/未装读屏的用户与演示场景；
  只在用户点击时播放，绝不自动出声，不干扰读屏用户
- 理科符号转译（第五阶段）：插件顶部双模式切换（默认转译），选中/粘贴一段
  含符号的原文即可转出读屏友好纯文本，可复制、可存历史、可一键转去理解模式；
  规则源自真实视障用户的 Accessibility Protocol 提示词清单

> 定位说明：这是「小有可为」AI 向善创新挑战赛（残健融合赛道）的最小可运行原型，
> 不是完整产品。不承诺教学、考试效果；无障碍体验需由视障用户实测把关。

## 第一层 vs 第二层能力说明

本项目分两层演进，第二层建立在第一层「结构树 + 中文朗读」的底座之上，不替换、不删除它。

| 维度 | 第一层：结构化朗读 | 第二层：教学型理解 |
|---|---|---|
| 目标 | 把公式「念清楚」（能听到） | 让人「听懂公式在干什么」（能理解） |
| 讲解顺序 | 按结构从外到内复述 | 先讲用途和直觉，再讲结构和符号 |
| 公式识别 | 不判断是什么公式 | 给出公式名称 / 领域 / 置信度 |
| 变量 | 逐字读符号 | 每个变量有角色与含义说明 |
| 领域知识 | 无 | 常见公式走模板 grounding（求根/傅里叶/导数/矩阵/大运算符/贝叶斯/期望方差/极限，共 8 类） |
| 未知公式 | 照常按结构读 | 走「谨慎解释」，标注「根据结构推断」并降低置信度；短小无上下文公式由 calibrate_confidence 后处理强制压低置信度 |
| 反流水账 | 不约束 | prompt 硬约束：禁止只复述「谁加谁谁乘谁」，每条理解必须回答「为什么/用来做什么」 |
| 兜底 | 本地规则朗读 | 无 Key 时本地规则也产出第二层 schema（基于模板知识，标 medium/low 置信度） |

第二层的领域知识只作为「知识锚点」交给大模型，模板本身不写死最终答案；
若锚点与实际公式不符，以实际公式为准并降低置信度。质量由
`scripts/explanation_quality_test.py` 做「反流水账」粗检。

## 快速开始

环境要求：Python 3.10+（已在 3.14 验证）；Node.js 为可选（仅 B 路线 SRE 需要）。

### Windows / PowerShell（推荐 `.venv`）

```powershell
cd math-a11y-assistant
python -m venv .venv                 # 首次：创建隔离虚拟环境
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .env.example .env               # 可选：填入 LLM_API_KEY（不配也能跑）

.\start.ps1                          # 一键启动（优先用 .venv，默认端口 8321）
```

> `start.ps1` 会自动优先调用 `.venv\Scripts\python.exe`，无需手动激活也能用正确的环境启动。
> PowerShell 5.1 不支持 `&&` 与三元运算符，脚本已按 `if/else` 编写，直接运行即可。

### 通用（bash / 手动启动）

```bash
cd math-a11y-assistant
pip install -r requirements.txt

# 可选：启用 B 路线（Speech Rule Engine 对比实验）
cd sre && npm install && cd ..

# 可选：配置大模型（不配也能跑，解释降级为本地规则版）
cp .env.example .env    # 然后填入 LLM_API_KEY

uvicorn app.main:app --port 8321
```

Windows 用户也可以直接双击项目目录里的 `启动服务.bat` 一键启动。

浏览器打开 http://127.0.0.1:8321 即可使用（详细命令行流程见 `docs/命令行启动与测试教程.md`）。

自测脚本：

```bash
python scripts/smoke_test.py                    # 解析引擎冒烟测试（3 个内置示例）
python scripts/api_test.py 8321                 # API 验收（需先启动服务）
python scripts/api_test.py --fast 8321          # 快速模式：跳过大模型，只验结构/链路
python scripts/physics_speech_test.py           # 物理/高数记号朗读回归
python scripts/explanation_quality_test.py 8321 # 第二层「反流水账」质量粗检（需先启动服务）
python scripts/eval_formula_set.py 8321         # 第三阶段：31 条样例批量评估，生成 eval_cases/latest_eval_report.md（约 10 分钟）
python scripts/language_quality_test.py 8321    # 第四阶段：讲解语言纯净度检查（中英混杂回归，4 条公式）
```

PowerShell 下也可直接用 `.\test_api.ps1`（加 `-Fast` 进快速模式）。

## 环境变量

见 `.env.example`。核心项：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `LLM_API_KEY` | 空 | 大模型 Key。空则解释/追问降级为本地规则，解析朗读不受影响 |
| `LLM_BASE_URL` | 百炼兼容模式地址 | 任何 OpenAI 兼容接口均可（DeepSeek 等只需改此项和模型名） |
| `LLM_MODEL` | `qwen3.7-plus,qwen-plus-latest,...` | 文本模型，支持逗号分隔备用链（见下） |
| `OCR_BACKEND` | `qwen-vl` | `qwen-vl` / `pix2text` / `none` |
| `OCR_VL_MODEL` | `qwen3-vl-plus,qwen-vl-max,...` | OCR 用视觉模型，同样支持备用链 |
| `TTS_MODEL` | `qwen3-tts-flash,qwen-tts` | 语音合成模型，同样支持备用链 |
| `TTS_VOICE` | `Cherry` | 音色，见百炼系统音色列表 |
| `TTS_API_URL` | 从 `LLM_BASE_URL` 推导 | TTS 原生端点，专属接入点自动兼容，一般不用填 |
| `PARSE_ENGINE` | `python` | 默认解析路线：`python` / `sre` |

代码中不出现任何密钥，Key 只从环境变量读取。

### 模型备用链与免费额度

百炼免费额度按模型 Code 独立计算（各 100 万 token）。`LLM_MODEL` 和 `OCR_VL_MODEL`
支持逗号分隔的备用链：某个模型额度用尽返回 403（`AllocationQuota.FreeTierOnly`）或
429 限流时，系统自动切换到链上下一个模型，开发过程无感。建议保持百炼控制台
「免费额度用完即停」开关开启，全程零成本。当前生效模型可通过 `GET /api/health` 查看。

## API 接口

所有接口输出稳定 JSON，`ok=false` 时带 `error` 字段。

### `GET /api/health`

各能力可用状态（llm / sre / ocr / tts / 默认引擎）。

### `GET /api/examples`

3 个内置示例：分式+根式（求根公式）、积分（傅里叶变换）、矩阵（线性方程组）。

### `POST /api/parse-latex`

```json
{"latex": "\\frac{1}{2}", "engine": "python", "with_explanation": true}
```

返回：`latex` / `mathml` / `tree`（结构树，节点含 id、role、label、text、spoken、children）/
`speech_text`（可朗读文本）/ `explanation`（第二层 schema，见下）/ `plain_text`（纯文本无障碍版）。

`explanation` 字段（第二层「教学型理解」）：`formula_name` / `domain` / `confidence`（high·medium·low）/
`purpose`（用来做什么）/ `intuition`（不含符号的直觉）/ `read_order` / `variables[]`（symbol·role·meaning）/
`structure_layers[]`（结构层）/ `concept_layers[]`（理解层）/ `common_misunderstandings[]` /
`suggested_questions[]` / `accessible_summary` / `source`。为兼容旧前端仍保留 `overview` 与 `layers`。

`engine=sre` 时朗读文本由 Speech Rule Engine 生成；SRE 不可用自动回退 python 路线并在
`engine_note` 中说明。

### `POST /api/explain`

只要分层解释：`{"latex": "..."}` → `{"ok": true, "explanation": {...}}`。

### `POST /api/ask`

针对公式或某个子结构追问：

```json
{"latex": "\\frac{a}{b}", "question": "分母是什么意思？", "node_id": "n2"}
```

`node_id` 来自结构树，可选；填了则回答聚焦该子结构。

### `POST /api/ocr-formula`

multipart 上传 `image`（png/jpg/webp/bmp，≤8MB），返回 `{latex, confidence, backend}`。
OCR 为可插拔设计（见 `app/ocr.py`）：

- `qwen-vl`（默认）：调用百炼视觉模型，无本地重依赖；不输出真实置信度，`confidence=null`。
- `pix2text`：本地开源模型，需 `pip install pix2text`（PyTorch 系重依赖，建议 Python
  3.10~3.12 环境；本机 3.14 可能装不上，属已知限制）。
- `none`：关闭，返回结构化「未启用」提示。

### `POST /api/tts`

文本转语音（百炼 Qwen-TTS 非流式）：`{"text": "分数线上面是 F…"}` → `audio/wav` 字节。

- 响应头：`X-TTS-Model`（实际模型）/ `X-TTS-Cached`（是否命中缓存）/ `X-TTS-Truncated`（是否被截断）。
- 后端代为下载 OSS 音频后返回字节，前端不接触临时 URL（免跨域、免 24 小时过期）；
  进程内缓存同文本重复播放不重复扣额度；文本超 500 字截断（模型上限 600）。
- 无 Key 时返回 422 结构化错误，前端降级提示改用系统朗读。
- 前台入口：Web 页与插件侧边栏的「听 AI 讲解」按钮（播 speech_text + 一段话总结，再按即停）。

### `POST /api/transcribe-symbols`

理科符号转译（转译模式后端）：把读屏不友好的符号转成 Unicode 纯文本，不解释、不客套。

```json
{
  "text": "已知函数 f(x)=sqrt(3x+1)，化学式 H2O 和 CO2 常见。",
  "source_type": "plain_text",
  "profile": "spoken_structured",
  "engine": null
}
```

返回 `{ok, mode: "symbol_transcription", profile, source_type, transcribed_text, confidence, source, applied, warnings}`。

- `profile` 支持两档：`unicode_compact` 输出紧凑 Unicode 纯文本，适合低视力用户和复制回文档；
  `spoken_structured` 输出结构朗读稿，适合主要依赖读屏的用户，例如把 `∫f(x)e^(−iωx)dx`
  转成“对 f(x) 乘以 e 的负 i 欧米伽 x 次方，关于 x 积分”。
- 双引擎策略：本地确定性规则优先（覆盖根号/对数/上下标/化学式/离子/几何/比较符/视觉积分等，
  零额度消耗、可离线、可复现）；规则转不净时自动切大模型（TRANSCRIBE_SYSTEM 提示词
  同样源自 Accessibility Protocol），失败再回退规则并把未转净记号写进 warnings。
  `engine` 可强制 `rules`/`llm`（测试脚本默认 rules 保证确定性）。
- 铁律由测试脚本强制检查：输出不得含 LaTeX 命令、客套话、解释性标题；
  宁可少转不乱转（拿不准的留在 warnings，不胡编）。
- 前台入口：插件侧边栏「转译原文」模式（主前台）与 Web 页顶部「符号转译」调试区。
- 回归用例：`eval_cases/symbol_transcription_cases.json`（34 条，覆盖根号/多次根号/上下标/
  对数/集合/几何/极限/积分/视觉公式/单位/温度防误转/化学式/离子/反应式），
  `python scripts/symbol_transcription_test.py 8321`。

### `POST /api/normalize-input`

把从网页/PDF/聊天窗口复制的普通公式文本转成 LaTeX：

```json
{"text": "x = (-b ± sqrt(b^2-4ac))/(2a)"}
```

返回 `{latex, confidence, notes, source}`。有 Key 时走大模型转换；无 Key 时用本地规则
兜底（sqrt/±/×÷/∞/π 等常见写法），规则转换一律标 `confidence=low`。前端将结果
填回方式一输入框由用户确认，不直接开始分析。

### `POST /api/compare`

A/B 双路线对比：同一公式分别返回纯 Python 路线与 SRE 路线的朗读文本和结构信息。

## A/B 双解析路线与实测结论

| | A：纯 Python | B：Speech Rule Engine（Node） |
|---|---|---|
| 链路 | latex2mathml → 自研结构树 + 中文朗读规则 | latex2mathml → SRE mathspeak |
| 依赖 | 无额外运行时 | Node.js + npm 包 |
| 中文效果 | 原生中文口语化（“分数，分子是…，分母是…”） | **zh-hans locale 实测仍输出英文 MathSpeak**（SRE 当前中文语音规则不完整） |
| 结构树 | 自研，节点可定位可追问 | 语义树更学术（stree XML） |

实测结论（2026-07，SRE 4.x）：SRE 的语义分析能力强，但中文朗读本地化缺失，
对中国视障学生不可直接用。因此默认走 A 路线，B 路线保留用于对比演示与后续研究
（这本身是参赛叙事里“为什么要做中文朗读层”的证据）。

### A 路线对物理/高数记号的语义化朗读

经真实物理公式（三维非稳态导热方程等）实测打磨，A 路线对以下记号按数学语义而非字面结构朗读：

- 导数：`\frac{\partial T}{\partial t}` 读「T 对 t 的偏导数」；纯算子 `\partial/\partial x` 读「对 x 求偏导」；
  高阶 `\partial^2 T/\partial x^2` 读「T 对 x 的 2 阶偏导数」；`dy/dx` 读「y 对 x 的导数」
- 上方记号：`\dot q` 读「q 点」、`\ddot x` 读「x 双点」、`\hat n` 读「n 帽」、`\bar x` 读「x 上横线」、`\vec F` 读「向量 F」
- 向量算子：`\nabla \cdot` 读「散度」、`\nabla \times` 读「旋度」、单独 `\cdot` 读「点乘」
- 粗体字母（`\mathbf{u}` 等 Unicode 数学字母变体）自动归一化，按物理惯例读「向量 u」

回归脚本：`python scripts/physics_speech_test.py`。7 例覆盖导数/记号/散度/旋度，并验证普通分数不受影响。

## 无障碍设计要点（前端）

- 语义化 HTML：标题层级、列表、fieldset/legend、role="status"。
- 全键盘可操作：所有功能均为原生 button/input；焦点样式高对比清晰可见。
- aria-label：每个按钮均有明确朗读文本；结果区通过 aria-live 播报状态。
- 跳转链接：页首「跳到分析结果」。
- 语音朗读为可选增强（浏览器 speechSynthesis），**不是唯一输出**，所有内容均有文本形式。
- 「复制纯文本解释」：一键复制适合粘贴到笔记/读屏环境的纯文本版。

注意：以上是工程层面的实现，最终无障碍体验必须用 NVDA / 手机读屏实测，并邀请
视障用户参与共创验证——这部分不在本原型范围内。

## 浏览器插件（第五阶段，产品主前台）

`extension/` 是 Chrome/Edge MV3 **侧边栏插件**，定位为日常主入口：学生在任意网页
（教材站、维基、题库）遇到公式，不离开原页面即可完成「捕获 → 确认 → 讲解 → 追问」。
Web 页（`static/index.html`）保留为调试演示台（结构树逐节点追问、A/B 对比等深功能）。

选型说明：用 Side Panel 而不是 Popup——Popup 一失焦就关闭，会打断读屏用户的
「确认→分析→追问」链路；侧边栏常驻，才是「伴随式理解层」。

加载方式（开发者模式）：

1. 先启动本机服务：双击 `启动服务.bat`，或命令行 `uvicorn app.main:app --port 8321`（插件默认连 `http://127.0.0.1:8321`；
   服务地址可在侧边栏底部「服务设置」里改，为将来后端部署云端预留）。
2. 浏览器打开 `chrome://extensions`（Edge 为 `edge://extensions`），开启「开发者模式」。
3. 「加载已解压的扩展程序」→ 选择 `math-a11y-assistant/extension/` 目录。
4. 点击工具栏图标打开侧边栏（首次可能需要在拼图菜单中固定图标）。

三种触发方式：

| 触发 | 操作 |
|---|---|
| 面板按钮 | 侧边栏内「提取本页公式」/「使用选中内容」/ 手动粘贴 |
| 右键菜单 | 选中公式文本 → 右键「用公式助手解释选中内容」 |
| 快捷键 | 选中公式文本 → `Alt+M` |

捕获优先级（能拿到源码就绝不识别）：KaTeX/MathJax v3 的 `annotation[x-tex]` →
MathJax v2 的 `script[type=math/tex]` → 维基公式图 `img.alt` → `math` 的 `alttext` →
裸 MathML 文本（走 `/api/normalize-input` 转换后确认）。所有捕获结果都先进
「识别待确认」编辑框（带本地朗读预览），用户确认后才开始分析——不确认不分析。

离线测试页：启动服务后访问 `http://127.0.0.1:8321/static/plugin_test_page.html`，
手工构造了上述 5 种公式 DOM 结构（不加载 CDN），预期「提取本页公式」找到 5 条。
信息架构与六状态机详见 `docs/plugin_information_architecture.md`。

已知限制：Firefox 侧边栏 API 不同（`sidebar_action`），当前 manifest 仅支持
Chromium 系浏览器；插件历史（`chrome.storage.local`，20 条）与 Web 页历史相互独立。

## 项目结构

```
math-a11y-assistant/
├── app/
│   ├── main.py              # FastAPI 路由（含 utf-8 响应中间件）
│   ├── config.py            # 环境变量
│   ├── llm.py               # 大模型调用 + 无 Key 规则兜底（第二层 schema）
│   ├── ocr.py               # 可插拔 OCR（qwen-vl / pix2text / none）
│   ├── examples.py          # 3 个内置示例
│   ├── knowledge/
│   │   └── templates.py     # 公式模板系统：为大模型提供领域知识锚点（grounding）
│   └── parser/
│       ├── python_engine.py # A 路线：结构树 + 中文朗读
│       └── sre_engine.py    # B 路线：SRE 子进程适配器
├── sre/
│   ├── package.json
│   └── sre_cli.js           # Node 桥：stdin MathML → stdout 朗读/语义树
├── static/
│   ├── index.html           # 无障碍前端（Web 调试演示台，支持 ?latex= 插件桥接）
│   └── plugin_test_page.html # 插件捕获离线测试页（5 种公式 DOM）
├── extension/               # 第五阶段：浏览器侧边栏插件（MV3，产品主前台）
│   ├── manifest.json        # sidePanel + contextMenus + Alt+M 快捷键
│   ├── background.js        # 触发路由：右键/快捷键 → 打开面板并投递选中内容
│   ├── content.js           # 按需注入的页面公式提取（IIFE，五层捕获优先级）
│   ├── sidepanel.html       # 面板 UI（第一屏四问：捕到什么/准不准/确认/下一步）
│   └── sidepanel.js         # 面板逻辑：捕获→确认→分析→追问→历史（六状态机）
├── scripts/
│   ├── smoke_test.py                 # 解析引擎冒烟测试
│   ├── api_test.py                   # API 验收测试（支持 --fast）
│   ├── physics_speech_test.py        # 物理/高数记号朗读回归
│   ├── explanation_quality_test.py   # 第二层「反流水账」质量粗检
│   ├── language_quality_test.py      # 第四阶段：讲解语言纯净度回归
│   └── eval_formula_set.py           # 第三阶段：样例集批量评估，产出 Markdown 报告
├── eval_cases/                   # 质量样例集：31 条公式 + 人工评分表 + OCR 验收图片/记录
├── docs/
│   ├── 命令行启动与测试教程.md   # Windows PowerShell 命令行教程
│   ├── 第二层交付报告.md          # 第二层交付总结
│   ├── plugin_information_architecture.md # 第五阶段：插件信息架构 + 六状态机
│   └── demo_script.md            # 8/13 初赛演示视频脚本（3 段）
├── start.ps1                # 一键启动（优先 .venv，默认端口 8321）
├── test_api.ps1             # PowerShell 版 API 测试（支持 -Fast）
├── requirements.txt
└── .env.example
```

## 使用的开源项目与许可证

| 项目 | 许可证 | 本项目中的用法 | 风险说明 |
|---|---|---|---|
| [latex2mathml](https://github.com/roniemartinez/latex2mathml) | MIT | 运行时依赖：LaTeX → MathML | 无风险，可闭源集成 |
| [Speech Rule Engine](https://github.com/Speech-Rule-Engine/speech-rule-engine) | Apache-2.0 | 可选运行时依赖（B 路线，子进程调用） | 低风险；需保留版权声明；专利授权友好 |
| [FastAPI](https://github.com/fastapi/fastapi) / [uvicorn](https://github.com/encode/uvicorn) / [httpx](https://github.com/encode/httpx) | MIT / BSD-3 | 后端框架与 HTTP 客户端 | 无风险 |
| [Pix2Text](https://github.com/breezedeus/Pix2Text) | MIT | 可选 OCR 后端（插件式，不装不影响） | 代码 MIT 无风险；注意其模型权重可能有单独条款，商用前需核对 |
| [LaTeX-OCR (pix2tex)](https://github.com/lukas-blecher/LaTeX-OCR) | MIT | 候选 OCR 后端（未集成，接口预留） | 同上，模型权重条款需单独核对 |
| [MathCAT](https://github.com/daisy/MathCAT) | MIT | 候选朗读底座（未集成；Rust 库，集成成本高于 SRE） | 无风险 |
| [Access8Math](https://github.com/tsengwoody/Access8Math) | GPL-2.0 | **仅作交互设计参考，未使用任何代码** | ⚠️ GPL 传染性：切勿复制其代码进本项目，否则整个项目须按 GPL 开源 |
| [MathJax](https://github.com/mathjax/MathJax) | Apache-2.0 | 未集成（当前用不到浏览器端渲染，后续视觉呈现可引入） | 低风险 |

Mathpix / InftyReader / MathKicker 为商业竞品，本项目未使用其任何 API 或代码。

## 已知限制（如实说明）

1. 未配置 `LLM_API_KEY` 时，分层解释为本地规则版（仍产出第二层 schema，但基于模板知识、较朴素，自由追问不可用）。
2. OCR 走 qwen-vl 时无真实置信度；Pix2Text 需要单独的 Python 3.10~3.12 环境。
3. 复杂/生僻 LaTeX（tikz、自定义宏包）不支持，会返回结构化错误提示。
4. SRE 路线中文本地化缺失（上游限制），当前主要用于对比研究。
5. 无障碍体验未经视障用户实测，属下一阶段共创工作。
