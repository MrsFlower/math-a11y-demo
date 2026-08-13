# -*- coding: utf-8 -*-
"""云端复验：251538c3（树优先三层兜底链）上传后验证。跑完保留为后续复验工具。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

BASE = "https://highcodzteceggb-azvgiimdkb.cn-beijing.fcapp.run"
TOKEN = "YOUR_FC_TRIGGER_TOKEN"

# (说明, 输入, profile, 必须包含, 禁止出现)
SAMPLES = [
    ("导数撇号 ODE（根治目标用例，必须走树）",
     "y'' - 4y' + 4y = e^{2x}", "spoken_structured",
     ["y 二阶导数", "y 一阶导数", "e 的 2 x 次方"], ["次方 减", "一撇"]),
    ("导数紧凑档（y″/y′ 规范撇号）",
     "y'' - 4y' + 4y = e^{2x}", "unicode_compact",
     ["y\u2033", "y\u2032", "e^(2x)"], ["次方"]),
    ("Unicode 撇号变体",
     "f\u2032(x) = 2x", "spoken_structured",
     ["f 一阶导数"], ["一撇 次方"]),
    ("点记号与向量",
     r"\dot{q} = \vec{u}", "spoken_structured",
     ["q 点", "向量 u"], []),
    ("定界符积分（dx 合并，不读 d x）",
     r"$\int_1^{+\infty} \frac{1}{x^2} dx$", "spoken_structured",
     ["从 1 到", "关于 x 积分"], ["d x"]),
    ("混排中文回正则（化学式不误伤）",
     "水的化学式是 H2O。", "unicode_compact",
     ["H\u2082O"], []),
    ("视觉大运算符回正则（树不碰伪结构）",
     "\u222b_{-\u221e}^{\u221e} f(x)e^(\u2212i\u03c9x) dx", "unicode_compact",
     ["积分(从-∞到", "e^(-iωx)"], ["^(()"]),
    ("历史回归守卫：极限读法",
     r"$\lim_{x \to 0} \frac{x - \sin x}{x^2 \ln(1+x)}$", "spoken_structured",
     ["lim(x→0)"], ["极限下标"]),
]

fails = 0
for desc, text, profile, must, banned in SAMPLES:
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
        fails += 1
        continue
    out = d.get("transcribed_text", "")
    problems = [m for m in must if m not in out] + [f"出现禁止「{b}」" for b in banned if b in out]
    if "\\" in out:
        problems.append("反斜杠残留")
    if "residue" not in d:
        problems.append("响应缺 residue 字段")
    tag = "PASS" if not problems else "FAIL"
    if problems:
        fails += 1
    print(f"{tag} [{desc}] source={d.get('source')}")
    print(f"     out: {out}")
    for p in problems:
        print(f"     - 缺少/问题: {p}")

print()
print("云端复验:", "全部通过" if fails == 0 else f"{fails} 处失败")
sys.exit(0 if fails else 1)
