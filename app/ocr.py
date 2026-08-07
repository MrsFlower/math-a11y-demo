"""阶段B：公式图片 OCR，可插拔后端。

后端选择（环境变量 OCR_BACKEND）：
- qwen-vl   ：调用百炼视觉模型（默认，无本地重依赖，需 LLM_API_KEY）。
- pix2text  ：本地开源模型（MIT），需另行 pip install pix2text，首次运行下载模型。
- none      ：关闭，接口返回「未启用」。

统一返回：{ok, latex, confidence, backend, error}
confidence 说明：qwen-vl 无法给出真实置信度，返回 None 并在字段中注明。
"""
from __future__ import annotations

import base64
import re

import httpx

from . import config

_TIMEOUT = httpx.Timeout(90.0, connect=10.0)

_VL_PROMPT = (
    "请识别图片中的数学公式，只输出该公式的 LaTeX 源码，"
    "不要输出任何解释、说明文字或代码块标记。若图中没有公式，输出 NO_FORMULA。"
)


def _clean_latex(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:latex|tex)?\s*|\s*```$", "", text).strip()
    # 去掉行内/行间数学定界符
    for pair in (("$$", "$$"), ("$", "$"), (r"\[", r"\]"), (r"\(", r"\)")):
        if text.startswith(pair[0]) and text.endswith(pair[1]):
            text = text[len(pair[0]): len(text) - len(pair[1])].strip()
    return text


def _ocr_qwen_vl(image_bytes: bytes, mime: str) -> dict:
    if not config.llm_available():
        return {
            "ok": False,
            "backend": "qwen-vl",
            "error": "OCR 后端 qwen-vl 需要配置 LLM_API_KEY（百炼）。",
        }
    b64 = base64.b64encode(image_bytes).decode("ascii")
    content = None
    last_error = None
    used_model = None
    # 沿 OCR_VL_MODELS 备用链重试：某个模型免费额度用尽（403/429）时切下一个
    for model in config.OCR_VL_MODELS:
        try:
            resp = httpx.post(
                f"{config.LLM_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                                },
                                {"type": "text", "text": _VL_PROMPT},
                            ],
                        }
                    ],
                    "temperature": 0,
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            used_model = model
            break
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code in (403, 429):
                continue
            raise
    if content is None:
        return {"ok": False, "backend": "qwen-vl", "error": f"所有视觉模型均不可用：{last_error}"}
    latex = _clean_latex(content)
    if not latex or latex == "NO_FORMULA":
        return {"ok": False, "backend": f"qwen-vl({used_model})", "error": "图片中未识别到公式。"}
    return {
        "ok": True,
        "latex": latex,
        "confidence": None,  # 大模型不输出可靠置信度，如实返回 None
        "backend": f"qwen-vl({used_model})",
        "error": None,
    }


def _ocr_pix2text(image_bytes: bytes, mime: str) -> dict:
    try:
        from pix2text import Pix2Text  # 延迟导入：重依赖，可选安装
    except ImportError:
        return {
            "ok": False,
            "backend": "pix2text",
            "error": "未安装 pix2text。请执行 pip install pix2text（需 Python 3.10~3.12 环境）。",
        }
    import io

    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    p2t = Pix2Text.from_config()
    result = p2t.recognize_formula(img, return_text=False)
    # recognize_formula 返回 dict：{'text': latex, 'score': 置信度}
    if isinstance(result, dict):
        latex = _clean_latex(result.get("text", ""))
        score = result.get("score")
    else:
        latex = _clean_latex(str(result))
        score = None
    if not latex:
        return {"ok": False, "backend": "pix2text", "error": "图片中未识别到公式。"}
    return {"ok": True, "latex": latex, "confidence": score, "backend": "pix2text", "error": None}


def ocr_formula(image_bytes: bytes, mime: str = "image/png") -> dict:
    """OCR 主入口，按 OCR_BACKEND 分发。"""
    backend = config.OCR_BACKEND
    if backend == "none":
        return {
            "ok": False,
            "backend": "none",
            "error": "OCR 未启用。设置环境变量 OCR_BACKEND=qwen-vl 或 pix2text 后可用。",
        }
    try:
        if backend == "qwen-vl":
            return _ocr_qwen_vl(image_bytes, mime)
        if backend == "pix2text":
            return _ocr_pix2text(image_bytes, mime)
    except Exception as exc:
        return {"ok": False, "backend": backend, "error": f"OCR 失败：{exc}"}
    return {"ok": False, "backend": backend, "error": f"未知 OCR 后端：{backend}"}
