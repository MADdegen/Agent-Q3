"""
Agent-Q3 Orchestrator — Main FastAPI App
MAD Gambit | github.com/MADdegen/Agent-Q3

Endpoints:
  POST /v1/chat    — auto-classify → Reasoner or Coder
  POST /v1/reason  — force Gemma4-E4B (instruct/reasoning)
  POST /v1/code    — force Qwen3.5-4B (code/fetch)
  GET  /health     — backend health summary
  GET  /metrics    — Prometheus metrics
"""

from contextlib import asynccontextmanager
from typing import Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .router import router, Backend
from .models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    Message,
    classify_task,
    REASONER_SYSTEM,
    CODER_SYSTEM,
)

log = structlog.get_logger(__name__)


# ── App lifespan ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Agent-Q3 starting",
        reasoner=settings.reasoner_model,
        coder=settings.coder_model,
        strategy=settings.compute_strategy,
    )
    yield
    log.info("Agent-Q3 shutting down")


app = FastAPI(
    title="Agent-Q3 Orchestrator",
    description="Dual-model orchestrator: Gemma4-E4B (Reasoning) + Qwen3.5-4B (Code/Fetch) with HF/RunPod routing",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Prometheus metrics ────────────────────────────────────────────────────────
Instrumentator().instrument(app).expose(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_messages(
    request: ChatRequest,
    system_override: Optional[str] = None,
) -> list[dict]:
    """Inject system prompt + convert Pydantic messages to dicts."""
    msgs = []
    system = system_override or request.system_prompt
    if system and not any(m.role == "system" for m in request.messages):
        msgs.append({"role": "system", "content": system})
    msgs.extend([m.model_dump() for m in request.messages])
    return msgs


def _extract_content(result: dict) -> str:
    """Normalise response content across all backends."""
    msg = result.get("message") or result.get("response") or {}
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {"service": "Agent-Q3", "version": "1.0.0", "docs": "/docs"}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Full health check — all backends + loaded models."""
    import httpx
    ollama_ok = False
    loaded_models = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                data = r.json()
                loaded_models = [m["name"] for m in data.get("models", [])]
    except Exception:
        pass

    return HealthResponse(
        status="ok" if ollama_ok else "degraded",
        ollama=ollama_ok,
        models_loaded=loaded_models,
        compute_strategy=settings.compute_strategy,
        backends={
            "local":       router._health[Backend.LOCAL].healthy,
            "huggingface": router._health[Backend.HF].healthy,
            "runpod":      router._health[Backend.RUNPOD].healthy,
        },
    )


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Auto-classify the request → routes to Reasoner or Coder.
    Set model_role='reasoner'|'coder' to force a model.
    Set force_backend='local'|'huggingface'|'runpod' to pin compute.
    """
    # Determine role
    if request.model_role == "auto" or request.model_role is None:
        role = classify_task(request.messages)
    else:
        role = request.model_role

    # Choose system prompt
    system = REASONER_SYSTEM if role == "reasoner" else CODER_SYSTEM
    messages = _build_messages(request, system_override=system)

    # Map force_backend string → enum
    force_backend = None
    if request.force_backend:
        force_backend = Backend(request.force_backend)

    try:
        result = await router.route(
            model_role=role,
            messages=messages,
            force_backend=force_backend,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        log.error("orchestration failed", error=str(e))
        raise HTTPException(status_code=503, detail=str(e))

    return ChatResponse(
        content=_extract_content(result),
        model_role=role,
        model_used=result.get("_model_used", "unknown"),
        backend_used=result.get("_backend_used", "unknown"),
        usage=result.get("usage"),
    )


@app.post("/v1/reason", response_model=ChatResponse)
async def reason(request: ChatRequest):
    """Force Gemma4-E4B — instruct, reasoning, research, planning."""
    request.model_role = "reasoner"
    return await chat(request)


@app.post("/v1/code", response_model=ChatResponse)
async def code(request: ChatRequest):
    """Force Qwen3.5-4B — code generation, fetch, debugging, file ops."""
    request.model_role = "coder"
    return await chat(request)


@app.post("/v1/tandem", response_model=dict)
async def tandem(request: ChatRequest):
    """
    Tandem mode: Gemma4-E4B reasons first → output fed to Qwen3.5-4B for implementation.
    Use for complex 'think + implement' tasks.
    """
    # Step 1: Reasoner analyses and produces a plan
    reason_msgs = _build_messages(request, system_override=REASONER_SYSTEM)
    try:
        reason_result = await router.route(
            model_role="reasoner",
            messages=reason_msgs,
            temperature=0.6,
            max_tokens=1024,
        )
        plan = _extract_content(reason_result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Reasoner failed: {e}")

    # Step 2: Coder implements the plan
    coder_msgs = [
        {"role": "system", "content": CODER_SYSTEM},
        *[m.model_dump() for m in request.messages],
        {"role": "assistant", "content": f"[Reasoning Plan]\n{plan}"},
        {"role": "user", "content": "Now implement this precisely. Return working code only."},
    ]
    try:
        code_result = await router.route(
            model_role="coder",
            messages=coder_msgs,
            temperature=0.3,
            max_tokens=request.max_tokens,
        )
        implementation = _extract_content(code_result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Coder failed: {e}")

    return {
        "plan": plan,
        "implementation": implementation,
        "reasoner_model": reason_result.get("_model_used"),
        "coder_model": code_result.get("_model_used"),
        "reasoner_backend": reason_result.get("_backend_used"),
        "coder_backend": code_result.get("_backend_used"),
    }
