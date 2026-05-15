"""Agent-Q3 - Triple-model orchestration API.

Stack:
  Reasoner: Qwen2.5-VL-32B-Instruct (multimodal, deep reasoning)
  Support:  Qwen3-8B Kimi-K2 Distilled (hybrid reasoning, punches above weight)
  Coder:    QwQ-32B (deep research, 131K ctx, coding)

Compute: Local Ollama -> HuggingFace Router -> RunPod -> OpenRouter

Claude Cowork integration:
  MCP endpoint:  /cowork/mcp
  Chat endpoint: /cowork/chat (OpenAI-compat)
  Memory:        /cowork/memory/*
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from .config import settings
from .models import ChatRequest, TandemRequest
from .router import ComputeRouter, multi_provider
from .cowork_ui import router as cowork_router
from .memory.agent_memory import get_memory_store
from .reasoning.decision_graph import get_decision_graph
from .observability.tracing import init_tracing

# Initialize
start_time = time.time()
logger = structlog.get_logger(__name__)
compute = ComputeRouter()
memory_store = get_memory_store()
decision_graph = get_decision_graph(compute)
tracer = init_tracing()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Agent-Q3 starting",
                reasoner=settings.reasoner_model,
                support=settings.support_model,
                coder=settings.coder_model,
                strategy=settings.compute_strategy)
    yield
    logger.info("Agent-Q3 shutting down")


app = FastAPI(
    title="Agent-Q3",
    description="Triple-model orchestration: Qwen2.5-VL-32B + Qwen3-8B-Kimi + QwQ-32B | Claude Cowork enabled",
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

# Mount Claude Cowork + MCP router
app.include_router(cowork_router)

# Multi-agent & CoWork
from .tools.composio_tools import get_composio_client
from .tools.multi_agent_router import MultiAgentRouter

composio_client = get_composio_client()
multi_agent_router = MultiAgentRouter(compute)

@app.get("/health")
async def health():
    await multi_provider.health_check()
    return {
        "status": "ok",
        "version": "0.3.0",
        "environment": settings.environment,
        "timestamp": datetime.utcnow().isoformat(),
        "uptime_seconds": time.time() - start_time,
        "strategy": settings.compute_strategy,
        "cowork_mcp": "/cowork/mcp",
        "memory": "/cowork/memory/recent",
        "hf_weekly_used": multi_provider.hf_weekly_used,
        "community_healthy": multi_provider.community_healthy,
        "openrouter_configured": bool(settings.openrouter_api_key),
        "runpod_serverless_configured": bool(settings.runpod_serverless_1),
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    try:
        response = await compute.chat(
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
        reasoner_task = compute.chat(
            messages=[{"role": "user", "content": req.research_prompt}],
            model_role="reasoner",
            max_tokens=req.max_tokens,
        )
        coder_task = compute.chat(
            messages=[{"role": "user", "content": req.code_prompt}],
            model_role="coder",
            max_tokens=req.max_tokens,
        )
        reasoner_resp, coder_resp = await asyncio.gather(reasoner_task, coder_task)
        return {"reasoner": reasoner_resp, "coder": coder_resp}
    except Exception as e:
        logger.error("tandem error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
      @app.get("/tools")
async def get_tools():
    """Expose all CoWork tools to LobeChat."""
    tools = await composio_client.get_all_tools()
    return {
        "tools": tools,
        "count": len(tools),
        "categories": ["github", "google_drive", "browser"],
    }


@app.post("/execute-tool")
async def execute_tool(req: dict):
    """Execute a Composio tool."""
    tool_name = req.get("tool_name")
    params = req.get("params", {})
    result = await composio_client.execute_tool(tool_name, params)
    return result


@app.post("/multi-agent")
async def multi_agent(req: dict):
    """Route through multi-agent orchestration with reasoning traces.
    
    Kimi can spawn Reasoner + Coder for complex tasks.
    Traces all decisions and tool execution.
    """
    query = req.get("query")
    context = req.get("context", {})
    conversation_id = req.get("conversation_id") or memory_store.create_conversation()
    
    # Log user message
    memory_store.add_message(conversation_id, "user", query)
    
    # Trace decision
    tracer.trace_reasoning_step("support", "analyze_query", query)
    
    # Run decision graph
    state = {
        "conversation_id": conversation_id,
        "query": query,
        "context": context,
        "should_spawn": False,
        "spawned_agents": [],
        "reasoner_result": None,
        "coder_result": None,
        "synthesis": None,
        "final_response": "",
    }
    
    result = await decision_graph.invoke(state)
    
    # Log assistant response
    memory_store.add_message(
        conversation_id,
        "assistant",
        result["final_response"],
        model_used="support",
    )
    
    return {
        "conversation_id": conversation_id,
        "multi_agent": result["should_spawn"],
        "spawned_agents": result.get("spawned_agents", []),
        "response": result["final_response"],
        "reasoning_traces": memory_store.get_reasoning_traces(conversation_id, limit=10),
    }
