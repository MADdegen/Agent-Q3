"""
Agent-Q3 — Dedicated Coder Service
Qwen3-Coder-30B-A3B-Instruct  (3B active MoE, ~96%+ HumanEval)
Supported by Hermes3 for code review / second-opinion

Endpoints:
  POST /v1/coder         — single-pass code generation (Qwen3-Coder)
  POST /v1/coder/review  — Qwen3-Coder writes → Hermes3 reviews → final
  GET  /health
"""

from contextlib import asynccontextmanager

import structlog
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from ..config import settings
from ..router import router, Backend, LOCAL_MODEL_MAP, HF_MODEL_MAP
from ..models import ChatRequest, ChatResponse, CODER_SYSTEM, HERMES_SYSTEM

log = structlog.get_logger(__name__)

# Register the dedicated coder role at module load
LOCAL_MODEL_MAP["coder_dedicated"] = lambda: settings.coder_dedicated_model
HF_MODEL_MAP["coder_dedicated"]    = lambda: settings.hf_coder_model

CODER_DEDICATED_SYSTEM = """You are a senior software engineer using Qwen3-Coder.
Write correct, idiomatic, production-grade code.

- Read the requirements precisely. Ask only if blocking ambiguity exists.
- Default to TypeScript for web, Python for scripts/ML, Solidity for contracts.
- Include only the comments that explain non-obvious WHY.
- Return working code. No filler prose, no apologies, no restating the prompt.
- If the request needs project context you don't have, state the assumption you made.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Coder service starting", model=settings.coder_dedicated_model)
    yield
    log.info("Coder service shutting down")


app = FastAPI(
    title="Agent-Q3 Coder Service",
    description="Dedicated Qwen3-Coder-30B-A3B endpoint with Hermes3 review tandem",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


def _build_messages(request: ChatRequest, system: str) -> list[dict]:
    msgs = []
    if system and not any(m.role == "system" for m in request.messages):
        msgs.append({"role": "system", "content": system})
    msgs.extend([m.model_dump() for m in request.messages])
    return msgs


def _extract(result: dict) -> str:
    msg = result.get("message") or result.get("response") or {}
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


@app.get("/")
async def root():
    return {
        "service": "Agent-Q3 Coder",
        "model": settings.coder_dedicated_model,
        "review_model": settings.tandem_model,
    }


@app.get("/health")
async def health():
    ok = False
    loaded = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                ok = True
                loaded = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return {
        "status": "ok" if ok else "degraded",
        "ollama": ok,
        "models_loaded": loaded,
        "primary_coder": settings.coder_dedicated_model,
    }


@app.post("/v1/coder", response_model=ChatResponse)
async def coder(request: ChatRequest):
    """Single-pass Qwen3-Coder-30B-A3B code generation."""
    messages = _build_messages(request, CODER_DEDICATED_SYSTEM)
    force_backend = Backend(request.force_backend) if request.force_backend else None
    try:
        result = await router.route(
            model_role="coder_dedicated",
            messages=messages,
            force_backend=force_backend,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        raise HTTPException(503, detail=str(e))
    return ChatResponse(
        content=_extract(result),
        model_role="coder_dedicated",
        model_used=result.get("_model_used", "unknown"),
        backend_used=result.get("_backend_used", "unknown"),
        usage=result.get("usage"),
    )


@app.post("/v1/coder/review", response_model=dict)
async def coder_review(request: ChatRequest):
    """
    Two-stage code generation:
      Stage 1 — Qwen3-Coder writes the code
      Stage 2 — Hermes3 reviews it (correctness, edge cases, style)
    """
    # Stage 1: Qwen3-Coder
    write_msgs = _build_messages(request, CODER_DEDICATED_SYSTEM)
    try:
        write_result = await router.route(
            model_role="coder_dedicated",
            messages=write_msgs,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
        code_out = _extract(write_result)
    except Exception as e:
        raise HTTPException(503, detail=f"Qwen3-Coder failed: {e}")

    # Stage 2: Hermes3 reviews
    review_msgs = [
        {"role": "system", "content": HERMES_SYSTEM},
        *[m.model_dump() for m in request.messages],
        {"role": "assistant", "content": f"[Qwen3-Coder draft]\n{code_out}"},
        {"role": "user", "content":
            "Review the code above. Identify bugs, edge cases, security issues, "
            "and idiom violations. If the code is correct, say so and explain why. "
            "If it needs changes, output the corrected version."},
    ]
    try:
        review_result = await router.route(
            model_role="tandem",
            messages=review_msgs,
            temperature=0.4,
            max_tokens=request.max_tokens,
        )
        review_out = _extract(review_result)
    except Exception as e:
        raise HTTPException(503, detail=f"Hermes review failed: {e}")

    return {
        "draft": code_out,
        "review": review_out,
        "coder_model":   write_result.get("_model_used"),
        "review_model":  review_result.get("_model_used"),
        "coder_backend": write_result.get("_backend_used"),
        "review_backend": review_result.get("_backend_used"),
    }
