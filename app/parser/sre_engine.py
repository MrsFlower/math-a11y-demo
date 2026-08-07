"""B 路线：Speech Rule Engine（Node.js）适配器。

通过子进程调用 sre/sre_cli.js，把 MathML 交给 SRE 生成朗读文本与语义树。
Node 或依赖缺失时优雅降级（available=False），不影响 A 路线。
"""
from __future__ import annotations

import json
import shutil
import subprocess

from .. import config


def sre_ready() -> tuple[bool, str]:
    """检查 SRE 路线是否可用，返回 (是否可用, 原因)。"""
    if shutil.which("node") is None:
        return False, "未检测到 Node.js，无法使用 SRE 路线。"
    if not config.SRE_CLI.exists():
        return False, "缺少 sre/sre_cli.js。"
    if not (config.SRE_DIR / "node_modules" / "speech-rule-engine").exists():
        return False, "尚未安装 SRE 依赖，请在 sre 目录执行 npm install。"
    return True, "ok"


def speak_mathml(mathml: str, timeout: float = 60.0) -> dict:
    """调用 SRE：返回 {available, speech_text, semantic_xml, locale, error}。"""
    ok, reason = sre_ready()
    if not ok:
        return {"available": False, "error": reason}

    payload = json.dumps(
        {"mathml": mathml, "locales": ["zh-hans", "zh-hant", "en"]}
    )
    try:
        proc = subprocess.run(
            ["node", str(config.SRE_CLI)],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=timeout,
            cwd=str(config.SRE_DIR),
        )
    except subprocess.TimeoutExpired:
        return {"available": True, "error": "SRE 子进程超时。"}

    stdout = proc.stdout.decode("utf-8", errors="replace").strip()
    try:
        result = json.loads(stdout)
    except json.JSONDecodeError:
        stderr = proc.stderr.decode("utf-8", errors="replace")[-500:]
        return {"available": True, "error": f"SRE 输出无法解析：{stdout[:200]} {stderr}"}

    if not result.get("ok"):
        return {"available": True, "error": result.get("error", "SRE 未知错误")}

    return {
        "available": True,
        "speech_text": result.get("speech", ""),
        "semantic_xml": result.get("semantic", ""),
        "locale": result.get("locale", ""),
        "error": None,
    }
