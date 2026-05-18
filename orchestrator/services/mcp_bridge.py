"""
Agent-Q3 — MCP Bridge service.

Single container exposing all configured MCP servers via a unified HTTP API.
The 3 app services + monitor call this bridge instead of opening MCP sessions
themselves — keeps connection pools tight and tool listings cached.

Endpoints:
  GET  /                   — service info
  GET  /health             — own health + per-MCP-server status
  GET  /mcp/servers        — list all configured + skipped MCP servers
  GET  /mcp/tools          — flat list of every tool across every server
  POST /mcp/call           — call a tool:  {"server": "...", "tool": "...", "args": {...}}
  POST /mcp/reload         — re-read .mcp.json and re-initialize
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from ..mcp_client import mcp_registry
from ..memory import memory

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("MCP Bridge starting")
    await memory.connect()
    await mcp_registry.load()
    yield
    await mcp_registry.close()
    await memory.close()
    log.info("MCP Bridge shutting down")


app = FastAPI(
    title="Agent-Q3 MCP Bridge",
    description="Unified gateway for all configured MCP servers",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


class CallRequest(BaseModel):
    server: str
    tool: str
    args: dict | None = None
    cache_ttl_secs: int = 0  # 0 = no caching


@app.get("/")
async def root():
    return {
        "service": "Agent-Q3 MCP Bridge",
        "memory_backend": memory.backend,
    }


@app.get("/health")
async def health():
    h = await mcp_registry.health()
    return {
        "status": "ok",
        "memory": await memory.ping(),
        "memory_backend": memory.backend,
        **h,
    }


@app.get("/mcp/servers")
async def servers():
    return await mcp_registry.health()


@app.get("/mcp/tools")
async def tools():
    by_server = await mcp_registry.list_all_tools()
    flat = []
    for srv, tlist in by_server.items():
        for t in tlist:
            flat.append({
                "server": srv,
                "name": t.get("name"),
                "description": t.get("description", ""),
                "schema": t.get("inputSchema", {}),
            })
    return {"count": len(flat), "tools": flat, "by_server": by_server}


@app.post("/mcp/call")
async def call(req: CallRequest):
    cache_key = None
    if req.cache_ttl_secs > 0:
        import hashlib, json as _json
        h = hashlib.sha256(
            _json.dumps({"s": req.server, "t": req.tool, "a": req.args}, sort_keys=True).encode()
        ).hexdigest()[:16]
        cache_key = f"mcp:{req.server}:{req.tool}:{h}"
        hit = await memory.cache_get(cache_key)
        if hit is not None:
            return {**hit, "_cached": True}

    result = await mcp_registry.call(req.server, req.tool, req.args)
    if "error" in result and "available" in result:
        raise HTTPException(404, detail=result)

    payload = {"server": req.server, "tool": req.tool, "result": result, "_cached": False}
    if cache_key:
        await memory.cache_set(cache_key, payload, ttl_secs=req.cache_ttl_secs)
    return payload


@app.post("/mcp/reload")
async def reload():
    await mcp_registry.close()
    info = await mcp_registry.load()
    return {"reloaded": True, **info}
