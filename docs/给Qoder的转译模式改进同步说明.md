# 给 Qoder 的转译模式改进同步说明

更新时间：2026-08-06

## 一、这次为什么要改

用户实测了一个公式：

```text
∫f(x)e^(−iωx)dx
```

旧版转译结果仍然是：

```text
∫f(x)e^(−iωx)dx
```

这说明第五阶段虽然已经做了“转译模式”的外壳，但核心能力还停留在“把 ASCII/LaTeX 记号转成 Unicode”，没有真正覆盖视障用户在网页、题目、论文里复制到的**视觉数学公式**。

真实问题不是“这个字符串有没有 Unicode”，而是：

> 读屏用户听到这串视觉符号时，能不能知道它的结构。

`∫`、指数作用范围、`dx`、隐式乘法、希腊字母这些内容，即使已经是 Unicode，对盲人用户仍然可能不可读或不可理解。转译模式必须从“字符替换器”升级成“读屏友好的结构转写器”。

## 二、产品判断的修正

现在转译模式拆成两个 profile：

1. `unicode_compact`
   - 紧凑 Unicode 纯文本。
   - 适合低视力用户、能看一点屏幕的用户，或需要把结果复制回文档的场景。
   - 例：`∫f(x)e^(−iωx)dx` -> `积分 f(x) × e^(-iωx)dx`

2. `spoken_structured`
   - 结构朗读稿。
   - 适合主要依赖读屏的盲人用户。
   - 例：`∫f(x)e^(−iωx)dx` -> `对 f(x) 乘以 e 的 负 i 欧米伽 x 次方，关于 x 积分`

注意：`spoken_structured` 仍然不是讲解模式。它不解释公式用途，不说“这是傅里叶变换”，不解题，只是把视觉结构线性化。

当前插件默认使用 `spoken_structured`，因为我们讨论的主路径是盲人用户遇到视觉公式后，需要先把结构听出来。

## 三、这次已经改了什么

### 1. 后端规则引擎

文件：

```text
app/transcriber.py
```

主要改动：

- 新增 `profile` 参数：`unicode_compact` / `spoken_structured`。
- 新增视觉积分规则：
  - `∫...dx`
  - `∫_{a}^{b} ... dx`
- 新增 Unicode 负号 `−` 规整为 `-`。
- 新增指数括号处理：
  - `e^(−iωx)` -> `e^(-iωx)`
  - 结构朗读时 -> `e 的 负 i 欧米伽 x 次方`
- 新增隐式乘法处理：
  - `f(x)e...` -> `f(x) × e...`
  - 避免把 `dx` 前面误加成乘号。
- 新增希腊字母朗读映射：
  - `ω` -> `欧米伽`
  - `α` -> `阿尔法`
  - `σ` -> `西格玛`
  - 等。
- 修复 LaTeX 规则顺序问题：
  - 旧逻辑会把 `\infty` 先命中 `\in`，变成 `∈fty`。
  - 现在 `\infty` 和 `\notin` 在 `\in` 之前处理。
- 修复复杂指数：
  - `2^(n-1)` 必须保留为 `2^(n-1)`，不能转成 `2ⁿ⁻¹`。

### 2. API 透传 profile

文件：

```text
app/main.py
app/llm.py
```

主要改动：

- `/api/transcribe-symbols` 接收并透传 `profile`。
- `llm.transcribe()` 支持 `profile`。
- 自动分流逻辑从“看原文 residue”改为“先跑规则，再看规则结果 residue”。

这个很重要。旧逻辑只看原文，视觉公式已经是 Unicode 时经常被误判为“没残留”，于是直接原样返回。

### 3. 插件前台

文件：

```text
extension/sidepanel.html
extension/sidepanel.js
```

主要改动：

- 插件新增“转译风格”：
  - 结构朗读，默认选中。
  - 紧凑文本。
- 转译请求会带上 `profile`。
- `looksLikeLatex()` 排除更多视觉数学符号：
  - `∫ ∑ ∏ ∂ ∇`
  - 希腊字母
  - Unicode 负号 `−`
  - 避免这些视觉公式在理解模式里被误判为 LaTeX。

### 4. Web 调试页

文件：

```text
static/index.html
```

主要改动：

- Web 顶部符号转译区也新增“结构朗读 / 紧凑文本”。
- 调试页不再只能测紧凑 Unicode。

### 5. 测试集

文件：

```text
eval_cases/symbol_transcription_cases.json
scripts/symbol_transcription_test.py
```

主要改动：

- 测试脚本支持每条 case 指定 `profile`。
- 用例从 30 条扩到 34 条。
- 新增视觉公式回归：
  - `∫f(x)e^(−iωx)dx`
  - `∫_{-∞}^{∞} f(x)e^(−iωx) dx`
  - `\int_{-\infty}^{\infty} f(x)e^{-i\omega x} dx`
  - `spoken_structured` 下的视觉傅里叶结构朗读。
- 加入 forbidden，防止再次出现：
  - 原样返回
  - `∈fty`
  - LaTeX 残留

## 四、验证结果

新代码在 `8322` 端口验证通过：

```text
python scripts/symbol_transcription_test.py 8322
结果：34/34 通过，0 失败。

python scripts/api_test.py --fast 8322
结果：13 通过 / 0 失败。

python scripts/language_quality_test.py 8322
结果：4 通过 / 0 失败。
```

定向样例：

```json
{
  "text": "∫f(x)e^(−iωx)dx",
  "profile": "spoken_structured",
  "engine": "rules"
}
```

返回：

```text
对 f(x) 乘以 e 的 负 i 欧米伽 x 次方，关于 x 积分
```

紧凑模式：

```json
{
  "text": "∫f(x)e^(−iωx)dx",
  "profile": "unicode_compact",
  "engine": "rules"
}
```

返回：

```text
积分 f(x) × e^(-iωx)dx
```

## 五、当前运行注意事项

用户原来的 `8321` 服务仍是旧进程，我没有强行关闭。

我用同一个 Python 3.14 解释器新起了 `8322` 做验证：

```text
C:\Users\15866\AppData\Local\Python\pythoncore-3.14-64\python.exe
```

如果要在插件里实际试新功能，需要：

1. 停掉旧的 `8321` 服务并重启，或临时把插件 API 改到 `8322`。
2. 到浏览器扩展管理页刷新插件。
3. 打开侧边栏确认能看到：
   - 工作模式：转译原文 / 理解公式
   - 转译风格：结构朗读 / 紧凑文本

## 六、下一步不要继续走偏

接下来不要只堆更多“字符替换表”。真正要补的是几类高频视觉结构：

1. 求和：
   - `∑_{i=1}^{n} aᵢ`
   - 结构朗读：从 i 等于 1 到 n，对 aᵢ 求和。

2. 偏导：
   - `∂T/∂t`
   - 结构朗读：T 对 t 的偏导数。

3. 根号视觉表达：
   - `√(x²+y²)`
   - 结构朗读：根号下 x 的平方加 y 的平方。

4. 分式视觉表达：
   - `(x+1)/(x+2)` 目前紧凑可接受，但结构朗读还应能说“分子是...，分母是...”。

5. Unicode 上下标反向朗读：
   - `aₙ₊₁`
   - 结构朗读应能说：a 下标 n 加 1。

6. 化学式在两档 profile 下的差异：
   - `unicode_compact`：`H₂SO₄`
   - `spoken_structured` 是否需要读成“硫酸，H 下标 2，S，O 下标 4”，需要和真实用户再确认。

## 七、产品红线

以后判断“转译模式是否完成”，不要只看 `sqrt`、`H2O`、`log_2`。

必须把下面这种已经是视觉公式的输入作为红线用例：

```text
∫f(x)e^(−iωx)dx
```

如果它再次原样返回，说明转译模式又退化成字符替换器了。

转译模式的目标不是“让字符串更漂亮”，而是：

> 让读屏用户能在线性听觉里获得原来靠视觉布局承载的结构信息。

