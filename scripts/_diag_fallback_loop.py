# -*- coding: utf-8 -*-
"""复核兜底闭环：residue 低置信度路径 + 强制 llm 在本地有 key 时的行为。"""
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def call(payload):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8321/api/transcribe-symbols",
        data=body, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


# 1) 规则转不净的内容：应 confidence=low/有 residue/warnings
d = call({"text": r"$\oint_C \vec{F} \cdot d\vec{r}$", "engine": "rules"})
print("residue 路径: confidence=", d.get("confidence"),
      " residue=", d.get("residue"), " warnings=", d.get("warnings"))

# 2) 强制 llm（本地已配 key）：应 source=llm、residue 为空
d2 = call({"text": r"$\oint_C \vec{F} \cdot d\vec{r}$", "engine": "llm"})
print("强制llm路径: source=", d2.get("source"), " confidence=", d2.get("confidence"),
      " residue=", d2.get("residue"), " warnings=", d2.get("warnings"))
print("out:", d2.get("transcribed_text", "")[:120])
