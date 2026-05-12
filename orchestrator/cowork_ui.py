from __future__ import annotations
"""
cowork_ui.py — Claude Cowork / Claude Desktop integration endpoints.

Exposes Agent-Q3 as a first-class MCP server + OpenAI-compatible API so that
Claude Cowork (desktop app) can connect directly via MCP or HTTP.

Endpoints:
  GET  /cowork/health         — ping + capabilities manifest
  POST /cowork/chat           — OpenAI-compat chat (used by Claude Cowork)
  GET  /cowork/mcp            — MCP server manifest (tools list)
  POST /cowork/mcp/tools/call — MCP tool execution
  GET  /cowork/memory/recent  — last 10 memories (for Cowork sidebar)
  POST /cowork/memory/save    — save memory from Cowork session
  GET  /cowork/memory/search  — semantic memory search

MCP Tools exposed to Claude Cowork:
  - agent_q3_reason    — send to Qwen2.5-VL-32B reasoner
  - agent_q3_research  — send to QwQ-32B deep research
  - agent_q3_support   — send to Qwen3-8B-Kimi support
  - memory_save        — persist a memory
  - memory_search      — semantic memory retrieval
  - deep_research      — Perplexity sonar-deep-research
  - web_search         — multi-provider web search
  - market_data        — Polymarket prediction market data
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Optional, List

from orchestrator.config import settings
from orchestrator.router import ComputeRouter
from orchestrator.tools.memory_store import MemoryStore
from orchestrator.tools.perplexity_search import perplexity_deep_research
from orchestrator.tools.web_search import multi_search
from orchestrator.tools.prediction_markets import get_polymarket_markets

router = APIRouter(prefix="/cowork", tags=["cowork"])
compute = ComputeRouter()
memory = MemoryStore()

AGENT_Q3_VERSION = "0.3.0"

# -- Capability manifest -----------------------------------------------------
CAPABILITIES = {
    "name": "Agent-Q3",
    "version": AGENT_Q3_VERSION,
    "description": "Triple-model AI agent: Qwen2.5-VL-32B (reasoner) + Qwen3-8B-Kimi (support) + QwQ-32B (coder/research)",
    "models": {
        "reasoner": settings.reasoner_model,
        "support": settings.support_model,
        "coder": settings.coder_model,
    },
    "tools": [
        "agent_q3_reason", "agent_q3_research", "agent_q3_support",
        "memory_save", "memory_search",
        "deep_research", "web_search", "market_data",
    ],
    "mcp_endpoint": "/cowork/mcp",
    "openai_compat_endpoint": "/cowork/chat",
    "memory": {
        "short_term": "Redis (24h TTL)",
        "long_term": "Postgres pgvector (384-dim nomic-embed-text)",
    },
}

MCP_TOOLS = [
    {
        "name": "agent_q3_reason",
        "description": "Send a prompt to the Qwen2.5-VL-32B multimodal reasoner. Best for: deep analysis, vision tasks, complex reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The prompt to reason about"},
                "system": {"type": "string", "description": "Optional system prompt"},
                "temperature": {"type": "number", "default": 0.7}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "agent_q3_research",
        "description": "Send a prompt to QwQ-32B deep research model (131K context). Best for: long-form research, code analysis, multi-step reasoning.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "system": {"type": "string"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "agent_q3_support",
        "description": "Send a prompt to Qwen3-8B Kimi-K2 distilled support model. Best for: fast instruct, hybrid reasoning, quick answers.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string"},
                "system": {"type": "string"}
            },
            "required": ["prompt"]
        }
    },
    {
        "name": "memory_save",
        "description": "Save a memory to Agent-Q3 persistent memory (Redis + Postgres pgvector).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Memory content to save"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "source": {"type": "string", "default": "cowork"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "memory_search",
        "description": "Semantic search over Agent-Q3 long-term memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "default": 5}
            },
            "required": ["query"]
        }
    },
    {
        "name": "deep_research",
        "description": "Run Perplexity sonar-deep-research for comprehensive multi-step web research with citations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "model": {"type": "string", "default": "sonar-deep-research"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "web_search",
        "description": "Multi-provider web search (Exa, Tavily, Brave, DuckDuckGo fallback).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "num_results": {"type": "integer", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "market_data",
        "description": "Fetch Polymarket prediction market data for research and conviction analysis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 10}
            },
            "required": []
        }
    },
]


# -- Routes ------------------------------------------------------------------

@router.get("/health")
async def cowork_health():
    return {"status": "ok", **CAPABILITIES}


@router.get("/mcp")
async def mcp_manifest():
    """MCP server manifest — Claude Cowork reads this to discover tools."""
    return {
        "protocol": "mcp",
        "version": "2025-11-05",
        "name": "agent-q3",
        "description": CAPABILITIES["description"],
        "tools": MCP_TOOLS,
    }


class MCPToolCall(BaseModel):
    name: str
    arguments: dict = {}


@router.post("/mcp/tools/call")
async def mcp_tool_call(call: MCPToolCall):
    """Execute an MCP tool call from Claude Cowork."""
    args = call.arguments

    if call.name == "agent_q3_reason":
        resp = await compute.chat(
            messages=[{"role": "user", "content": args["prompt"]}],
            model_role="reasoner",
            temperature=args.get("temperature", 0.7),
        )
        return {"content": [{"type": "text", "text": str(resp)}]}

    elif call.name == "agent_q3_research":
        resp = await compute.chat(
            messages=[{"role": "user", "content": args["prompt"]}],
            model_role="coder",
        )
        return {"content": [{"type": "text", "text": str(resp)}]}

    elif call.name == "agent_q3_support":
        resp = await compute.chat(
            messages=[{"role": "user", "content": args["prompt"]}],
            model_role="support",
        )
        return {"content": [{"type": "text", "text": str(resp)}]}

    elif call.name == "memory_save":
        mem_id = await memory.save(
            text=args["text"],
            tags=args.get("tags", []),
            source=args.get("source", "cowork"),
        )
        return {"content": [{"type": "text", "text": f"Memory saved: {mem_id}"}]}

    elif call.name == "memory_search":
        results = await memory.search(args["query"], k=args.get("k", 5))
        return {"content": [{"type": "text", "text": str(results)}]}

    elif call.name == "deep_research":
        result = await perplexity_deep_research(
            query=args["query"],
            model=args.get("model", "sonar-deep-research"),
        )
        return {"content": [{"type": "text", "text": str(result)}]}

    elif call.name == "web_search":
        results = await multi_search(args["query"], max_results=args.get("num_results", 10))
        return {"content": [{"type": "text", "text": str(results)}]}

    elif call.name == "market_data":
        markets = await get_polymarket_markets(
            limit=args.get("limit", 10),
            query=args.get("query"),
        )
        return {"content": [{"type": "text", "text": str(markets)}]}

    raise HTTPException(status_code=404, detail=f"Unknown tool: {call.name}")


# -- Memory convenience routes -----------------------------------------------

@router.get("/memory/recent")
async def memory_recent(n: int = 10):
    return await memory.get_recent(n)


class MemorySaveRequest(BaseModel):
    text: str
    tags: List[str] = []
    source: str = "cowork"


@router.post("/memory/save")
async def memory_save(req: MemorySaveRequest):
    mem_id = await memory.save(req.text, req.tags, req.source)
    return {"id": mem_id, "status": "saved"}


@router.get("/memory/search")
async def memory_search_route(q: str, k: int = 5):
    results = await memory.search(q, k=k)
    return {"results": results}
