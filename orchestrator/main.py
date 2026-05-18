"""
Agent-Q3 Orchestrator — Main FastAPI App
MAD Gambit | github.com/MADdegen/Agent-Q3

Model stack:
  [1] Kimi-VL-A3B-Instruct i1 Q4_K_M  — primary instruct + vision  → /v1/instruct
  [2] Hermes3 8B                        — tandem reasoning partner   → /v1/tandem (step 1)
  [3] Qwen3-48B-A4B-Savant Q6_K        — primary multimodal         → /v1/code
  [4] Qwopus3.6-27B Q8_0               — fallback multimodal        → /v1/fallback

Composite endpoints:
  POST /v1/chat     — auto-classify → instruct or multimodal
  POST /v1/instruct — force Kimi-VL (vision, long-ctx, agent tasks)
  POST /v1/code     — force Qwen3-48B (multimodal, code, fetch)
  POST /v1/tandem   — Kimi reasons → Hermes refines → Qwen implements
  POST /v1/fallback — force Qwopus3.6-27B
  GET  /health      — all backends + loaded models
  GET  /metrics     — Prometheus
"""

from contextlib import asynccontextmanager

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
    HERMES_SYSTEM,
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Agent-Q3 starting",
        instruct=settings.reasoner_model,
        tandem=settings.tandem_model,
        multimodal=settings.coder_model,
        fallback=settings.fallback_model,
        strategy=settings.compute_strategy,
    )
    yield
    log.info("Agent-Q3 shutting down")


app = FastAPI(
    title="Agent-Q3 Orchestrator",
    description=(
        "4-model orchestrator: "
        "Kimi-VL-A3B (instruct/vision) + Hermes3 (tandem) + "
        "Qwen3-48B-A4B (multimodal) + Qwopus3.6-27B (fallback)"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_messages(
    request: ChatRequest,
    system_override: str | None = None,
) -> list[dict]:
    msgs = []
    system = system_override or request.system_prompt
    if system and not any(m.role == "system" for m in request.messages):
        msgs.append({"role": "system", "content": system})
    msgs.extend([m.model_dump() for m in request.messages])
    return msgs


def _extract_content(result: dict) -> str:
    msg = result.get("message") or result.get("response") or {}
    if isinstance(msg, dict):
        return msg.get("content", "")
    return str(msg)


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    return {
        "service": "Agent-Q3",
        "version": "2.0.0",
        "docs": "/docs",
        "models": {
            "instruct":   settings.reasoner_model,
            "tandem":     settings.tandem_model,
            "multimodal": settings.coder_model,
            "fallback":   settings.fallback_model,
        }
    }


@app.get("/health", response_model=HealthResponse)
async def health():
    """Full health check — all backends + loaded Ollama models."""
    import httpx as _httpx
    ollama_ok = False
    loaded_models = []
    try:
        async with _httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            if r.status_code == 200:
                ollama_ok = True
                loaded_models = [m["name"] for m in r.json().get("models", [])]
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
    Auto-classify → instruct (Kimi-VL) or multimodal (Qwen3-48B).
    Override with model_role='reasoner'|'coder'|'tandem'|'fallback'.
    Pin compute with force_backend='local'|'huggingface'|'runpod'.
    """
    if request.model_role in (None, "auto"):
        role = classify_task(request.messages)
    else:
        role = request.model_role

    system = REASONER_SYSTEM if role == "reasoner" else CODER_SYSTEM
    messages = _build_messages(request, system_override=system)

    force_backend = Backend(request.force_backend) if request.force_backend else None

    try:
        result = await router.route(
            model_role=role,
            messages=messages,
            force_backend=force_backend,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        log.error("chat failed", error=str(e))
        raise HTTPException(status_code=503, detail=str(e))

    return ChatResponse(
        content=_extract_content(result),
        model_role=role,
        model_used=result.get("_model_used", "unknown"),
        backend_used=result.get("_backend_used", "unknown"),
        usage=result.get("usage"),
    )


@app.post("/v1/instruct", response_model=ChatResponse)
async def instruct(request: ChatRequest):
    """Force Kimi-VL-A3B — vision, long-context, agent, instruct tasks."""
    request.model_role = "reasoner"
    messages = _build_messages(request, system_override=REASONER_SYSTEM)
    force_backend = Backend(request.force_backend) if request.force_backend else None
    try:
        result = await router.route(
            model_role="reasoner",
            messages=messages,
            force_backend=force_backend,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ChatResponse(
        content=_extract_content(result),
        model_role="reasoner",
        model_used=result.get("_model_used", "unknown"),
        backend_used=result.get("_backend_used", "unknown"),
        usage=result.get("usage"),
    )


@app.post("/v1/reason", response_model=ChatResponse)
async def reason(request: ChatRequest):
    """Alias for /v1/instruct — forces Kimi-VL-A3B."""
    return await instruct(request)


@app.post("/v1/code", response_model=ChatResponse)
async def code(request: ChatRequest):
    """Force Qwen3-48B-A4B-Savant — primary multimodal, code, fetch, structured output."""
    messages = _build_messages(request, system_override=CODER_SYSTEM)
    force_backend = Backend(request.force_backend) if request.force_backend else None
    try:
        result = await router.route(
            model_role="coder",
            messages=messages,
            force_backend=force_backend,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ChatResponse(
        content=_extract_content(result),
        model_role="coder",
        model_used=result.get("_model_used", "unknown"),
        backend_used=result.get("_backend_used", "unknown"),
        usage=result.get("usage"),
    )


@app.post("/v1/fallback", response_model=ChatResponse)
async def fallback(request: ChatRequest):
    """Force Qwopus3.6-27B — fallback multimodal when primary is overloaded."""
    messages = _build_messages(request, system_override=CODER_SYSTEM)
    force_backend = Backend(request.force_backend) if request.force_backend else None
    try:
        result = await router.route(
            model_role="fallback",
            messages=messages,
            force_backend=force_backend,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))
    return ChatResponse(
        content=_extract_content(result),
        model_role="fallback",
        model_used=result.get("_model_used", "unknown"),
        backend_used=result.get("_backend_used", "unknown"),
        usage=result.get("usage"),
    )


@app.post("/v1/tandem", response_model=dict)
async def tandem(request: ChatRequest):
    """
    3-stage tandem pipeline:
      Stage 1 — Kimi-VL-A3B reads the prompt, produces analysis + plan (vision aware)
      Stage 2 — Hermes3 refines the plan with deep reasoning
      Stage 3 — Qwen3-48B-A4B implements the refined plan

    Use for complex tasks that need vision → reasoning → implementation.
    """
    force_backend = Backend(request.force_backend) if request.force_backend else None

    # Stage 1: Kimi-VL — read + initial analysis
    kimi_msgs = _build_messages(request, system_override=REASONER_SYSTEM)
    try:
        kimi_result = await router.route(
            model_role="reasoner",
            messages=kimi_msgs,
            force_backend=force_backend,
            temperature=0.6,
            max_tokens=1024,
        )
        kimi_analysis = _extract_content(kimi_result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Kimi-VL (Stage 1) failed: {e}")

    # Stage 2: Hermes3 — deep reasoning on Kimi's analysis
    hermes_msgs = [
        {"role": "system", "content": HERMES_SYSTEM},
        *[m.model_dump() for m in request.messages],
        {"role": "assistant", "content": f"[Kimi-VL Analysis]\n{kimi_analysis}"},
        {"role": "user", "content": "Reason through this carefully. Identify any gaps or improvements in the analysis above, then produce a precise, refined implementation plan."},
    ]
    try:
        hermes_result = await router.route(
            model_role="tandem",
            messages=hermes_msgs,
            force_backend=force_backend,
            temperature=0.5,
            max_tokens=1024,
        )
        hermes_plan = _extract_content(hermes_result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Hermes3 (Stage 2) failed: {e}")

    # Stage 3: Qwen3-48B — implement the refined plan
    qwen_msgs = [
        {"role": "system", "content": CODER_SYSTEM},
        *[m.model_dump() for m in request.messages],
        {"role": "assistant", "content": f"[Kimi-VL Analysis]\n{kimi_analysis}\n\n[Hermes3 Refined Plan]\n{hermes_plan}"},
        {"role": "user", "content": "Implement this precisely. Return working, production-ready output only."},
    ]
    try:
        qwen_result = await router.route(
            model_role="coder",
            messages=qwen_msgs,
            force_backend=force_backend,
            temperature=0.3,
            max_tokens=request.max_tokens,
        )
        implementation = _extract_content(qwen_result)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Qwen3-48B (Stage 3) failed: {e}")

    return {
        "kimi_analysis":     kimi_analysis,
        "hermes_plan":       hermes_plan,
        "implementation":    implementation,
        "kimi_model":        kimi_result.get("_model_used"),
        "hermes_model":      hermes_result.get("_model_used"),
        "qwen_model":        qwen_result.get("_model_used"),
        "kimi_backend":      kimi_result.get("_backend_used"),
        "hermes_backend":    hermes_result.get("_backend_used"),
        "qwen_backend":      qwen_result.get("_backend_used"),
    }
