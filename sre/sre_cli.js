/**
 * Speech Rule Engine 命令行桥。
 *
 * 用法：node sre_cli.js
 *   stdin  : JSON {"mathml": "<math>...</math>", "locales": ["zh-hans","zh-hant","en"]}
 *   stdout : JSON {"ok":true,"speech":"...","semantic":"<stree>...","locale":"实际生效locale"}
 *
 * 说明：SRE 的中文 locale 支持随版本变化，这里按优先级逐个尝试，
 *       某个 locale 初始化失败或产出为空时自动回退到下一个。
 */
const sre = require('speech-rule-engine');

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (chunk) => (data += chunk));
    process.stdin.on('end', () => resolve(data));
    process.stdin.on('error', reject);
  });
}

async function trySetup(locale) {
  await sre.setupEngine({
    locale,
    domain: 'mathspeak',
    modality: 'speech',
    markup: 'none',
    style: 'default',
  });
  await sre.engineReady();
}

async function main() {
  const raw = await readStdin();
  const input = JSON.parse(raw);
  const mathml = input.mathml;
  const locales = input.locales || ['zh-hans', 'zh-hant', 'en'];
  if (!mathml) throw new Error('缺少 mathml 字段');

  let speech = '';
  let usedLocale = '';
  let lastError = null;
  const hasCJK = (s) => /[\u4e00-\u9fff]/.test(s);
  for (const locale of locales) {
    try {
      await trySetup(locale);
      const out = sre.toSpeech(mathml);
      if (out && out.trim()) {
        // 优先采用真正含中文的输出（部分 locale 会静默回退英文规则）
        if (!speech || (hasCJK(out) && !hasCJK(speech))) {
          speech = out;
          usedLocale = locale;
        }
        if (hasCJK(out)) break;
      }
    } catch (err) {
      lastError = err;
    }
  }
  if (!speech || !speech.trim()) {
    throw lastError || new Error('SRE 未能生成朗读文本');
  }

  let semantic = '';
  try {
    const semNode = sre.toSemantic(mathml);
    semantic = semNode && semNode.toString ? semNode.toString() : String(semNode);
  } catch (err) {
    semantic = ''; // 语义树失败不影响朗读结果
  }

  process.stdout.write(
    JSON.stringify({ ok: true, speech: speech.trim(), semantic, locale: usedLocale })
  );
}

main().catch((err) => {
  process.stdout.write(JSON.stringify({ ok: false, error: String(err && err.message ? err.message : err) }));
  process.exit(0); // 错误也走 stdout JSON，方便 Python 侧统一处理
});
