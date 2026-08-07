"""数学公式无障碍学习助手 - FastAPI 主入口。

启动：uvicorn app.main:app --reload
接口：
  GET  /health            百炼高代码应用平台探活（轻量）
  GET  /api/health        健康检查（含各能力可用状态）
  GET  /api/examples      内置示例公式
  POST /api/parse-latex   LaTeX -> 结构树 + 朗读文本 + 分层解释（一次到位）
  POST /api/normalize-input 普通公式文本/中文描述 -> LaTeX（不直接分析，交用户确认）
  POST /api/explain       LaTeX -> 仅分层中文解释
  POST /api/ask           针对公式/子结构追问
  POST /api/ocr-formula   公式图片 -> LaTeX（阶段B，可插拔后端）
  POST /api/tts           文本 -> 语音（wav 字节，百炼 Qwen-TTS，不自动播放）
  POST /api/transcribe-symbols 理科符号 -> 读屏友好纯文本（第五阶段转译模式，不解释）
  POST /api/compare       A/B 双引擎对比（python vs SRE）
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, llm, ocr, tts
from .examples import EXAMPLES
from .parser import python_engine, sre_engine

app = FastAPI(
    title="数学公式无障碍学习助手",
    description="面向视障学生：把公式从「能听到」推进到「能听懂」。",
    version="0.1.0",
)

# 第五阶段：浏览器插件（chrome-extension:// 源）作为前台调用本服务。
# 服务仅监听 127.0.0.1，放行所有来源无安全风险，且免去枚举扩展 ID。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _utf8_json(request, call_next):
    """JSON 响应显式声明 utf-8，避免 Windows PowerShell 5.1 等客户端按 ISO-8859-1 解码乱码。"""
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if not STATIC_DIR.is_dir():
    # 百炼高代码部署时 wheel 只含 Python 包，静态页随 app/static 子包安装
    STATIC_DIR = Path(__file__).resolve().parent / "static"


# ---------------- 请求模型 ----------------

class LatexIn(BaseModel):
    latex: str = Field(..., description="LaTeX 公式源码", max_length=5000)
    engine: str | None = Field(None, description="解析引擎：python / sre，缺省用环境变量配置")
    with_explanation: bool = Field(True, description="是否同时生成大模型分层解释")
    context: str | None = Field(
        None, description="公式所在页面的上下文文字（插件提取时顺带抓取），仅用于消歧义", max_length=600
    )


class AskIn(BaseModel):
    latex: str = Field(..., max_length=5000)
    question: str = Field(..., description="学生的追问", max_length=1000)
    node_id: str | None = Field(None, description="聚焦的结构树节点 id，如 n3")


class NormalizeIn(BaseModel):
    text: str = Field(..., description="从网页/PDF/聊天复制的公式文本，或中文口语描述", max_length=2000)


class TtsIn(BaseModel):
    text: str = Field(..., description="要朗读的中文文本（超长会截断）", max_length=4000)


class SymbolTranscribeIn(BaseModel):
    text: str = Field(..., description="含读屏不友好理科符号的原文片段", max_length=12000)
    source_type: str | None = Field("plain_text", description="来源类型：plain_text / selection / ocr 等，仅记录用")
    profile: str | None = Field("unicode_compact", description="转译风格：unicode_compact / spoken_structured")
    engine: str | None = Field(
        None, description="强制引擎：rules 纯规则 / llm 强制大模型；缺省自动（规则覆盖得住就不花额度）"
    )


# ---------------- 工具函数 ----------------

def _err(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _plain_text_version(latex: str, speech: str, explanation: dict) -> str:
    """生成「复制纯文本解释」用的无障碍纯文本版，顺序与前端/schema 一致。"""
    exp = explanation
    lines: list[str] = ["【公式朗读】", speech, ""]

    name = exp.get("formula_name")
    if name:
        conf = exp.get("confidence")
        domain = exp.get("domain")
        tail = "（领域：%s；置信度：%s）" % (domain, conf) if (domain or conf) else ""
        lines += ["【这是什么公式】", f"{name}{tail}", ""]
    if exp.get("purpose"):
        lines += ["【它用来解决什么问题】", exp["purpose"], ""]
    if exp.get("intuition"):
        lines += ["【直觉解释】", exp["intuition"], ""]
    if exp.get("read_order"):
        lines += ["【建议听读顺序】"]
        lines += [f"{i}. {step}" for i, step in enumerate(exp["read_order"], 1)]
        lines += [""]
    if exp.get("variables"):
        lines += ["【变量说明】"]
        for v in exp["variables"]:
            lines.append(f"- {v.get('symbol', '')}（{v.get('role', '')}）：{v.get('meaning', '')}")
        lines += [""]

    struct = exp.get("structure_layers") or exp.get("layers") or []
    if struct:
        lines += ["【结构层级】"]
        for i, layer in enumerate(struct, 1):
            lines.append(f"{i}. {layer.get('title', '')}")
            lines.append(f"   {layer.get('content', '')}")
        lines += [""]
    if exp.get("concept_layers"):
        lines += ["【概念理解】"]
        for i, layer in enumerate(exp["concept_layers"], 1):
            lines.append(f"{i}. {layer.get('title', '')}")
            lines.append(f"   {layer.get('content', '')}")
        lines += [""]
    if exp.get("common_misunderstandings"):
        lines += ["【常见误解】"]
        lines += [f"- {m}" for m in exp["common_misunderstandings"]]
        lines += [""]

    questions = exp.get("suggested_questions", [])
    if questions:
        lines += ["【可以继续追问】"]
        lines += [f"- {q}" for q in questions]
        lines += [""]
    if exp.get("accessible_summary"):
        lines += ["【一段话总结】", exp["accessible_summary"], ""]
    lines += ["【原始 LaTeX】", latex]
    return "\n".join(lines)


def _parse_with_engine(latex: str, engine: str) -> dict:
    """统一解析：python 路线必跑（结构树是解释的基础），sre 路线按需补充朗读。"""
    base = python_engine.parse_latex(latex)
    result = {
        "latex": latex,
        "mathml": base["mathml"],
        "tree": base["tree"],
        "speech_text": base["speech_text"],
        "engine": "python",
    }
    if engine == "sre":
        sre_out = sre_engine.speak_mathml(base["mathml"])
        if sre_out.get("speech_text"):
            result["speech_text"] = sre_out["speech_text"]
            result["engine"] = f"sre（locale={sre_out.get('locale', '?')}）"
            result["sre_semantic_xml"] = sre_out.get("semantic_xml", "")
        else:
            result["engine_note"] = f"SRE 不可用，已回退纯 Python 路线：{sre_out.get('error')}"
    return result


# ---------------- API ----------------

@app.get("/health")
def health_probe():
    """百炼高代码应用部署规范要求的平台探活接口（不可调通则判定启动失败）。
    完整能力状态请看 /api/health。"""
    return "OK"


@app.get("/api/health")
def health():
    sre_ok, sre_reason = sre_engine.sre_ready()
    return {
        "ok": True,
        "llm": {
            "available": config.llm_available(),
            "model": llm.current_model(),
            "fallback_chain": config.LLM_MODELS,
        },
        "sre": {"available": sre_ok, "note": sre_reason},
        "ocr": {"backend": config.OCR_BACKEND, "models": config.OCR_VL_MODELS},
        "tts": {"available": config.llm_available(), "models": config.TTS_MODELS, "voice": config.TTS_VOICE},
        "default_engine": config.PARSE_ENGINE,
    }


@app.get("/api/examples")
def examples():
    return {"ok": True, "examples": EXAMPLES}


@app.post("/api/parse-latex")
def parse_latex(body: LatexIn):
    engine = (body.engine or config.PARSE_ENGINE).lower()
    try:
        result = _parse_with_engine(body.latex.strip(), engine)
    except ValueError as exc:
        return _err(str(exc))

    if body.with_explanation:
        explanation = llm.explain(result["latex"], result["tree"], result["speech_text"], context=body.context)
    else:
        explanation = {"overview": "", "layers": [], "suggested_questions": [], "source": "skipped"}

    return {
        "ok": True,
        **result,
        "explanation": explanation,
        "plain_text": _plain_text_version(result["latex"], result["speech_text"], explanation),
    }


@app.post("/api/explain")
def explain(body: LatexIn):
    try:
        base = python_engine.parse_latex(body.latex.strip())
    except ValueError as exc:
        return _err(str(exc))
    explanation = llm.explain(body.latex.strip(), base["tree"], base["speech_text"], context=body.context)
    return {"ok": True, "explanation": explanation}


@app.post("/api/ask")
def ask(body: AskIn):
    try:
        base = python_engine.parse_latex(body.latex.strip())
    except ValueError as exc:
        return _err(str(exc))

    node_text = None
    if body.node_id:
        node = python_engine.find_node(base["tree"], body.node_id)
        if node:
            node_text = f"[{node['label']}] {node['text']}（读作：{node['spoken']}）"
    result = llm.ask(body.latex.strip(), base["tree"], body.question.strip(), node_text)
    return {"ok": True, **result}


@app.post("/api/normalize-input")
def normalize_input(body: NormalizeIn):
    """普通文本转 LaTeX：只做格式转换不做分析，结果填回输入框由用户确认。"""
    text = body.text.strip()
    if not text:
        return _err("请先粘贴公式文本。")
    result = llm.normalize_text(text)
    if not result.get("latex"):
        return _err(result.get("notes") or "未识别出公式，请检查输入，也可以改用粘贴 LaTeX 或上传图片。", status=422)
    return {"ok": True, **result}


@app.post("/api/ocr-formula")
async def ocr_formula(image: UploadFile = File(...)):
    if image.content_type not in ("image/png", "image/jpeg", "image/webp", "image/bmp"):
        return _err(f"不支持的图片类型：{image.content_type}，请上传 png/jpg/webp/bmp。")
    data = await image.read()
    if len(data) > 8 * 1024 * 1024:
        return _err("图片超过 8MB，请压缩后再试。")
    result = ocr.ocr_formula(data, image.content_type)
    if not result.get("ok"):
        return _err(result.get("error", "OCR 失败"), status=422)
    return {"ok": True, **{k: v for k, v in result.items() if k != "ok"}}


@app.post("/api/tts")
def tts_synthesize(body: TtsIn):
    """文本转语音：返回 wav 字节。供「听讲解」按钮用，前端绝不自动播放。"""
    result = tts.synthesize(body.text)
    if not result.get("ok"):
        return _err(result.get("error", "语音合成失败"), status=422)
    return Response(
        content=result["audio"],
        media_type="audio/wav",
        headers={
            "X-TTS-Model": result.get("model", ""),
            "X-TTS-Cached": "1" if result.get("cached") else "0",
            "X-TTS-Truncated": "1" if result.get("truncated") else "0",
            "Cache-Control": "no-store",
        },
    )


@app.post("/api/transcribe-symbols")
def transcribe_symbols(body: SymbolTranscribeIn):
    """理科符号转译（第五阶段）：读屏不友好的符号 -> Unicode 纯文本，不解释、不客套。"""
    result = llm.transcribe(body.text, engine=body.engine, profile=body.profile or "unicode_compact")
    if not result.get("ok"):
        return _err(result.get("error", "转译失败"))
    return {
        "ok": True,
        "mode": "symbol_transcription",
        "profile": body.profile or "unicode_compact",
        "source_type": body.source_type or "plain_text",
        **{k: v for k, v in result.items() if k != "ok"},
    }


@app.post("/api/compare")
def compare(body: LatexIn):
    """A/B 路线对比：同一公式分别给出两条路线的朗读文本，便于评估选型。"""
    latex = body.latex.strip()
    try:
        base = python_engine.parse_latex(latex)
    except ValueError as exc:
        return _err(str(exc))

    sre_out = sre_engine.speak_mathml(base["mathml"])
    return {
        "ok": True,
        "latex": latex,
        "python_route": {
            "speech_text": base["speech_text"],
            "tree_outline": python_engine.tree_outline(base["tree"]),
        },
        "sre_route": {
            "available": sre_out.get("available", False),
            "speech_text": sre_out.get("speech_text", ""),
            "locale": sre_out.get("locale", ""),
            "semantic_xml": sre_out.get("semantic_xml", ""),
            "error": sre_out.get("error"),
        },
    }


# ---------------- 静态前端 ----------------

@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
