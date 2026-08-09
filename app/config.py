"""全局配置：统一从环境变量读取，支持 .env 文件。"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---- 大模型（OpenAI 兼容接口，默认阿里云百炼）----
# 兼容百炼高代码控制台的模板字段 DASHSCOPE_API_KEY（官方 starter 惯例），
# 本机 .env 继续用 LLM_API_KEY，两者任一配置即可
LLM_API_KEY = (os.getenv("LLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or "").strip()
LLM_BASE_URL = os.getenv(
    "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).rstrip("/")
# 支持逗号分隔的备用链：百炼免费额度按模型 Code 独立计算（各 100 万 token），
# 某个模型额度用尽返回 403 时自动切换到下一个。
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.7-plus,qwen-plus-latest,qwen3.5-plus,qwen-flash")
LLM_MODELS = [m.strip() for m in LLM_MODEL.split(",") if m.strip()]

# ---- 阶段B：公式图片 OCR ----
OCR_BACKEND = os.getenv("OCR_BACKEND", "qwen-vl").strip().lower()  # qwen-vl / pix2text / none
OCR_VL_MODEL = os.getenv("OCR_VL_MODEL", "qwen3-vl-plus,qwen-vl-max,qwen3-vl-flash")
OCR_VL_MODELS = [m.strip() for m in OCR_VL_MODEL.split(",") if m.strip()]

# ---- 语音合成（Qwen-TTS，走百炼原生端点而非 compatible-mode）----
TTS_MODEL = os.getenv("TTS_MODEL", "qwen3-tts-flash,qwen-tts")
TTS_MODELS = [m.strip() for m in TTS_MODEL.split(",") if m.strip()]
TTS_VOICE = os.getenv("TTS_VOICE", "Cherry").strip()

# ---- 应用层 API 鉴权 ----
# FC 触发器改匿名后（静态展示页需公网可开），由应用自己守住 /api/*，防算力被滥用。
# 默认值与插件内置 token 一致；也可用环境变量 API_AUTH_TOKEN 覆盖。
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN", "258697c6-125d-40d0-943d-38c7bb817b5a").strip()
# 端点从 LLM_BASE_URL 的 origin 推导（兼容专属接入点），也可用环境变量直接覆盖
_llm_origin = "/".join(LLM_BASE_URL.split("/")[:3]) or "https://dashscope.aliyuncs.com"
TTS_API_URL = os.getenv(
    "TTS_API_URL", f"{_llm_origin}/api/v1/services/aigc/multimodal-generation/generation"
).strip()

# ---- 解析引擎默认路线 ----
PARSE_ENGINE = os.getenv("PARSE_ENGINE", "python").strip().lower()  # python / sre

# ---- SRE（Node.js）----
SRE_DIR = BASE_DIR / "sre"
SRE_CLI = SRE_DIR / "sre_cli.js"


def llm_available() -> bool:
    return bool(LLM_API_KEY)
