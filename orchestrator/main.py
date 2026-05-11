"""Agent-Q3 — Dual-model orchestration API.

Tandem: Gemma4-E4B (Reasoner) + Qwen3.5-4B (Coder)
Compute: Local Ollama -> HuggingFace Router -> RunPod -> OpenRouter
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .models import ChatRequest, TandemRequest
from .router import ComputeRouter

logger = structlog.get_logger(__name__)
router = ComputeRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: warm router. Shutdown: cleanup."""
    logger.info("Agent-Q3 starting",
                reasoner=settings.reasoner_model,
                coder=settings.coder_model,
                strategy=settings.compute_strategy)
    yield
    logger.info("Agent-Q3 shutting down")


app = FastAPI(
    title="Agent-Q3 Orchestrator",
    description="Dual-model tandem: Gemma4-E4B (Reasoner) + Qwen3.5-4B (Coder)",
    version="3.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)


@app.get("/")
@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "agent-q3",
        "version": "3.0.0",
        "models": {
            "reasoner": settings.reasoner_model,
            "coder": settings.coder_model,
        },
        "strategy": settings.compute_strategy,
        "backends": {
            "local": True,
            "hf_router": settings.has_hf(),
            "runpod": settings.has_runpod(),
            "openrouter": settings.has_openrouter(),
        },
    }


@app.post("/v1/chat")
async def chat(req: ChatRequest) -> Dict[str, Any]:
    """Auto-classified chat — routes to reasoner or coder based on content."""
    from .models import classify_task
    role = req.model_role if req.model_role != "auto" else classify_task(req.messages)
    model = settings.reasoner_model if role == "reasoner" else settings.coder_model
    result = await router.complete(
        model=model,
        messages=[m.dict() for m in req.messages],
        max_tokens=req.max_tokens or 2048,
        force_backend=req.force_backend,
    )
    return {**result, "model_role": role}


@app.post("/v1/reason")
async def reason(req: ChatRequest) -> Dict[str, Any]:
    """Force Reasoner agent (Gemma4-E4B): deep research, analysis, market insight."""
    result = await router.complete(
        model=settings.reasoner_model,
        messages=[m.dict() for m in req.messages],
        max_tokens=req.max_tokens or 4096,
        force_backend=req.force_backend,
    )
    return {**result, "model_role": "reasoner"}


@app.post("/v1/code")
async def code(req: ChatRequest) -> Dict[str, Any]:
    """Force Coder agent (Qwen3.5-4B): code generation, fetch, file ops."""
    result = await router.complete(
        model=settings.coder_model,
        messages=[m.dict() for m in req.messages],
        max_tokens=req.max_tokens or 4096,
        force_backend=req.force_backend,
    )
    return {**result, "model_role": "coder"}


@app.post("/v1/tandem")
async def tandem(req: TandemRequest) -> Dict[str, Any]:
    """Tandem mode: Reasoner researches, Coder implements, results merged."""
    import asyncio
    reason_task = router.complete(
        model=settings.reasoner_model,
        messages=[{"role": "user", "content": req.research_prompt}],
        max_tokens=req.max_tokens or 2048,
    )
    code_task = router.complete(
        model=settings.coder_model,
        messages=[{"role": "user", "content": req.code_prompt}],
        max_tokens=req.max_tokens or 2048,
    )
    reason_res, code_res = await asyncio.gather(reason_task, code_task)
    return {
        "reasoner": reason_res,
        "coder": code_res,
        "tandem": True,
        "platform_fee": "1.88%",
    }


@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    """List available models across all backends."""
    return {
        "local": [settings.reasoner_model, settings.coder_model],
        "hf_router": [settings.hf_reasoner_model, settings.hf_coder_model],
        "runpod_endpoint": settings.runpod_reasoner_endpoint_id,
    }
