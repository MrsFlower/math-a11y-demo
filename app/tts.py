"""语音合成（TTS）：百炼 Qwen-TTS 非流式 HTTP 调用。

定位：给「没装读屏/低视力/演示」场景一个自带声音的播放按钮。
铁律不变：绝不自动播放，读屏用户不点它就完全无感，不和 NVDA 打架。

接口形态（百炼原生端点，非 compatible-mode）：
  POST /api/v1/services/aigc/multimodal-generation/generation
  {"model": "qwen3-tts-flash", "input": {"text", "voice", "language_type"}}
  响应 output.audio.url（wav，24h 有效）或 output.audio.data（Base64）。

设计决策：
- 后端代为下载音频再返回字节，前端不接触 OSS URL（免跨域、免 24h 过期问题）。
- 进程内小缓存（同文本重复播放不重复扣免费额度）。
- 文本超长截断到 500 字（qwen3-tts-flash 上限 600 字符，留余量）。
"""
from __future__ import annotations

import base64
import hashlib
from collections import OrderedDict

import httpx

from . import config

_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

MAX_CHARS = 500
_CACHE_MAX = 24
_cache: OrderedDict[str, tuple[bytes, str]] = OrderedDict()  # key -> (wav字节, 模型名)


def _cache_put(key: str, value: tuple[bytes, str]) -> None:
    _cache[key] = value
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


def synthesize(text: str) -> dict:
    """文本 -> wav 字节。返回 {ok, audio, model, cached, truncated} 或 {ok, error}。"""
    if not config.llm_available():
        return {"ok": False, "error": "语音合成需要配置 LLM_API_KEY（百炼）。"}
    text = " ".join(text.split()).strip()
    if not text:
        return {"ok": False, "error": "没有可朗读的文本。"}
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]

    key = hashlib.sha1(f"{config.TTS_VOICE}|{text}".encode("utf-8")).hexdigest()
    if key in _cache:
        audio, model = _cache[key]
        return {"ok": True, "audio": audio, "model": model, "cached": True, "truncated": truncated}

    last_error: Exception | None = None
    # 沿 TTS_MODELS 备用链重试：额度用尽（403/429）时切下一个，与 ocr.py 同款策略
    for model in config.TTS_MODELS:
        try:
            resp = httpx.post(
                config.TTS_API_URL,
                headers={
                    "Authorization": f"Bearer {config.LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "input": {"text": text, "voice": config.TTS_VOICE, "language_type": "Chinese"},
                },
                timeout=_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            audio_info = (payload.get("output") or {}).get("audio") or {}
            audio = _fetch_audio(audio_info)
            if audio is None:
                last_error = RuntimeError(f"{model} 响应中没有音频：{payload.get('message') or payload}")
                continue
            _cache_put(key, (audio, model))
            return {"ok": True, "audio": audio, "model": model, "cached": False, "truncated": truncated}
        except httpx.HTTPStatusError as exc:
            last_error = exc
            if exc.response.status_code in (403, 429):
                continue
            break
        except httpx.HTTPError as exc:
            last_error = exc
            break
    return {"ok": False, "error": f"语音合成失败：{last_error}"}


def _fetch_audio(audio_info: dict) -> bytes | None:
    """从响应的 audio 对象取音频：优先内联 Base64，否则下载 OSS URL。"""
    data = audio_info.get("data") or ""
    if data:
        try:
            return base64.b64decode(data)
        except Exception:
            return None
    url = audio_info.get("url") or ""
    if url:
        resp = httpx.get(url, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.content
    return None
