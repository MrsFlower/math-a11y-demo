# eval_cases：真实公式质量样例集

第三阶段引入的质量评估资产。目标不是「更多测试」，而是回答一个问题：
**系统的讲解是否可信、是否知道自己什么时候不确定。**

## 目录内容

| 文件 | 用途 |
|---|---|
| `formulas.json` | 31 条真实公式样例，覆盖 6 大类（见下） |
| `manual_review_template.md` | 人工评分表模板（每条 6 维度 1-5 分） |
| `latest_eval_report.md` | 批量评估脚本生成的最新报告（自动覆盖） |
| `ocr_images/` | OCR 真实验收图片与记录 |

## 样例覆盖

- 高中代数（5）：求根公式、韦达定理、等差/等比数列、二次函数。
- 微积分（7）：导数定义、偏导、定/不定积分、极限、傅里叶、泰勒。
- 线性代数（4）：矩阵、线性方程组、矩阵乘法、行列式。
- 概率统计（5）：条件概率、贝叶斯、期望、方差、正态密度。
- 物理数学（5）：牛顿第二定律、热传导、波动方程、高斯定律、质能方程。
- 上下文不足/未知（5）：`a+b=c` 等，用于验证保守表达。

## 字段说明

```json
{
  "id": "唯一标识，domain_name_编号",
  "title": "人类可读名称",
  "latex": "输入公式",
  "domain": "期望领域",
  "expected_keywords": ["讲解全文里期望出现的关键词（记录命中率，不作硬性 FAIL）"],
  "avoid_overclaim": "true=上下文不足样例，confidence 出现 high 即为风险",
  "expected_confidence": "low_or_medium（仅 avoid_overclaim=true 时有）",
  "notes": "这条样例在考察什么"
}
```

注意：`F=ma`、`E=mc^2` 虽是著名公式，但按保守机制设计，短小无上下文的公式
置信度会被校准压低并标注「根据结构推断」——报告里看到 low 不是 bug，是特性。

## 如何运行批量评估

```powershell
# 先启动服务（默认 8321），然后：
python scripts/eval_formula_set.py 8321
```

- 报告输出到 `eval_cases/latest_eval_report.md`。
- 31 条 × 每条约 20 秒（大模型生成），全程约 10 分钟。
- 脚本退出码：`avoid_overclaim=true` 的样例出现 `confidence=high` 时非零（验收红线）。

## 人工评审流程

1. 跑一次批量评估，通读 `latest_eval_report.md`，标记可疑样例。
2. 复制 `manual_review_template.md` 为 `manual_review_YYYYMMDD.md`。
3. 对可疑样例 + 抽样 5~10 条正常样例逐条打分。
4. 「是否需要模板增强」「是否适合放进演示视频」两栏用于反哺开发和录制。
