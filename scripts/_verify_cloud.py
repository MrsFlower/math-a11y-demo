# -*- coding: utf-8 -*-
"""云端复验：9cc0aeae 包上传后，验证兜底闭环 + 新规则在云端生效。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE = "https://highcodzteceggb-azvgiimdkb.cn-beijing.fcapp.run"
TOKEN = "YOUR_FC_TRIGGER_TOKEN"

# (说明, 输入, profile)
SAMPLES = [
    ("函数名规则 \\sin/\\ln（2a3c24db 会落 LLM 兜底）",
     r"是 $\sin^2 x$ 的（ ）。当 $x \to 0$ 时 $f(x) = \ln(1 + x^2)$", "spoken_structured"),
    ("lim 500 修复 + 减号空格（大极限公式）",
     r"$\lim_{x \to 0} \frac{x - \sin x}{x^2 \ln(1+x)}$", "spoken_structured"),
    ("求根公式回归（结构朗读）",
     r"x = (-b ± sqrt(b^2-4ac))/(2a)", "spoken_structured"),
    ("矩阵新规则（9cc0aeae 才有）",
     r"\begin{bmatrix} 1 & 2 \\ 3 & 4 \end{bmatrix}", "unicode_compact"),
]

ok_all = True
for desc, text, profile in SAMPLES:
    body = json.dumps({"text": text, "profile": profile, "engine": "rules"}).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/api/transcribe-symbols", data=body,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {TOKEN}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"FAIL [{desc}] 请求异常: {e}")
        ok_all = False
        continue
    out = d.get("transcribed_text", "")
    residue = d.get("residue")
    has_backslash = "\\" in out
    # 9cc0aeae 起响应必须携带 residue 字段（前端兜底区依赖）
    has_residue_field = "residue" in d
    print(f"[{desc}]")
    print(f"  out: {out}")
    print(f"  residue: {residue}  反斜杠残留: {has_backslash}  响应含residue字段: {has_residue_field}")
    if has_backslash or not has_residue_field:
        ok_all = False
    # 极限读法回归断言（9cc0aeae 曾退化成「极限下标 x →0」）
    if desc.startswith("lim"):
        if "lim(x→0)" not in out or "极限下标" in out:
            print("  FAIL: 极限读法回归，期望 lim(x→0) 且不含「极限下标」")
            ok_all = False
    print()

print("云端复验:", "全部通过" if ok_all else "存在问题")
sys.exit(0 if ok_all else 1)
