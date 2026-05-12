"""Agent-Q3 - Triple-model orchestration API.

Stack:
  Reasoner: Qwen2.5-VL-32B-Instruct (multimodal, deep reasoning)
  Support:  Qwen3-8B Kimi-K2 Distilled (hybrid reasoning, punches above weight)
  Coder:    QwQ-32B (deep research, 131K ctx, coding)

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
                support=settings.support_model,
                coder=settings.coder_model,
                strategy=settings.compute_strategy)
    yield
    logger.info("Agent-Q3 shutting down")


app = FastAPI(
    title="Agent-Q3",
    description="Triple-model orchestration: Qwen2.5-VL-32B + Qwen3-8B-Kimi + QwQ-32B",
    version="0.3.0",
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


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "models": {
            "reasoner": settings.reasoner_model,
            "support": settings.support_model,
            "coder": settings.coder_model,
        },
        "strategy": settings.compute_strategy,
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        response = await router.chat(
            messages=[m.dict() for m in req.messages],
            model_role=req.model_role,
            force_backend=req.force_backend,
            max_tokens=req.max_tokens,
            temperature=req.temperature,
            stream=req.stream,
        )
        return response
    except Exception as e:
        logger.error("chat error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/tandem")
async def tandem(req: TandemRequest):
    """Run reasoner + coder in parallel, return both responses."""
    try:
        import asyncio
        reasoner_task = router.chat(
            messages=[{"role": "user", "content": req.research_prompt}],
            model_role="reasoner",
            max_tokens=req.max_tokens,
        )
        coder_task = router.chat(
            messages=[{"role": "user", "content": req.code_prompt}],
            model_role="coder",
            max_tokens=req.max_tokens,
        )
        reasoner_resp, coder_resp = await asyncio.gather(reasoner_task, coder_task)
        return {"reasoner": reasoner_resp, "coder": coder_resp}
    except Exception as e:
        logger.error("tandem error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
