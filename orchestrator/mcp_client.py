"""
Agent-Q3 — Minimal MCP (Model Context Protocol) client.

Supports the streamable-HTTP transport (the modern MCP standard). Reads server
declarations from /app/.mcp.json. For each HTTP MCP, it speaks JSON-RPC 2.0
over POST.

stdio transport (e.g. playwright via npx) is NOT supported by this client —
the mcp-bridge container exposes those via HTTP wrappers separately.

The bridge service holds a singleton MCPRegistry. App services (multimodal /
coder / research / monitor) call the bridge over HTTP; they do NOT instantiate
MCP clients themselves.
"""

import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
import structlog

log = structlog.get_logger(__name__)

MCP_CONFIG_PATH = Path("/app/.mcp.json")


class MCPHTTPClient:
    """Single MCP server connection over streamable HTTP (JSON-RPC 2.0)."""

    def __init__(self, name: str, url: str, auth_header: dict[str, str] | None = None,
                 description: str = ""):
        self.name = name
        self.url = url.rstrip("/")
        self.description = description
        self.auth_header = auth_header or {}
        self._session_id: Optional[str] = None
        self._tools_cache: list[dict] = []
        self._client = httpx.AsyncClient(timeout=30)
        self._initialized: bool = False
        self._last_error: Optional[str] = None

    async def _rpc(self, method: str, params: dict | None = None) -> dict:
        """Send a JSON-RPC request and return the response."""
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": method,
        }
        if params is not None:
            payload["params"] = params

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.auth_header,
        }
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id

        r = await self._client.post(self.url, json=payload, headers=headers)
        r.raise_for_status()

        # Capture session id from initialization response
        sid = r.headers.get("Mcp-Session-Id")
        if sid and not self._session_id:
            self._session_id = sid

        # Server may respond with text/event-stream or application/json
        ctype = r.headers.get("content-type", "")
        if "text/event-stream" in ctype:
            # Read SSE — first data: line is the response
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    return json.loads(line[5:].strip())
        return r.json()

    async def initialize(self) -> bool:
        try:
            resp = await self._rpc("initialize", {
                "protocolVersion": "2025-06-18",
                "capabilities": {"roots": {"listChanged": False}, "sampling": {}},
                "clientInfo": {"name": "agent-q3-mcp-bridge", "version": "1.0.0"},
            })
            if "error" in resp:
                self._last_error = str(resp["error"])
                log.warning("MCP init failed", server=self.name, error=resp["error"])
                return False
            # Send the "notifications/initialized" notification per spec
            try:
                await self._rpc("notifications/initialized")
            except Exception:
                pass
            self._initialized = True
            return True
        except Exception as e:
            self._last_error = str(e)
            log.warning("MCP init exception", server=self.name, error=str(e))
            return False

    async def list_tools(self) -> list[dict]:
        try:
            resp = await self._rpc("tools/list")
            tools = resp.get("result", {}).get("tools", [])
            self._tools_cache = tools
            return tools
        except Exception as e:
            self._last_error = str(e)
            log.warning("MCP tools/list failed", server=self.name, error=str(e))
            return []

    async def call_tool(self, tool: str, args: dict | None = None) -> dict:
        try:
            resp = await self._rpc("tools/call", {
                "name": tool,
                "arguments": args or {},
            })
            if "error" in resp:
                return {"error": resp["error"]}
            return resp.get("result", {})
        except Exception as e:
            self._last_error = str(e)
            return {"error": str(e)}

    async def health(self) -> dict:
        return {
            "name": self.name,
            "url": self.url,
            "initialized": self._initialized,
            "tools_count": len(self._tools_cache),
            "last_error": self._last_error,
        }

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass


class MCPRegistry:
    """Loads .mcp.json, connects to every HTTP MCP server, caches their tools."""

    def __init__(self, config_path: Path = MCP_CONFIG_PATH):
        self.config_path = config_path
        self._clients: dict[str, MCPHTTPClient] = {}
        self._skipped: dict[str, str] = {}
        self._loaded_at: float = 0

    async def load(self) -> dict:
        cfg = {}
        if self.config_path.exists():
            try:
                cfg = json.loads(self.config_path.read_text(encoding="utf-8"))
            except Exception as e:
                log.error("mcp.json parse failed", error=str(e))
                return {"servers": [], "skipped": {".mcp.json": str(e)}}

        servers = cfg.get("mcpServers", {})
        init_tasks = []

        for name, conf in servers.items():
            transport = conf.get("type", "http")
            if transport == "stdio":
                self._skipped[name] = "stdio transport — handled by bridge subprocess pool"
                continue
            url = conf.get("url")
            if not url:
                self._skipped[name] = "no url"
                continue

            auth = {}
            auth_block = conf.get("auth", {})
            if auth_block.get("type") == "bearer":
                import os
                env_key = auth_block.get("env", "")
                token = os.getenv(env_key, "") if env_key else ""
                if token:
                    auth["Authorization"] = f"Bearer {token}"
                else:
                    self._skipped[name] = f"missing env {env_key}"
                    continue

            client = MCPHTTPClient(name=name, url=url, auth_header=auth,
                                   description=conf.get("description", ""))
            self._clients[name] = client
            init_tasks.append(self._init_one(client))

        if init_tasks:
            await asyncio.gather(*init_tasks, return_exceptions=True)

        self._loaded_at = time.time()
        log.info("MCP registry loaded",
                 active=list(self._clients.keys()),
                 skipped=list(self._skipped.keys()))
        return {
            "servers": list(self._clients.keys()),
            "skipped": self._skipped,
        }

    async def _init_one(self, client: MCPHTTPClient) -> None:
        ok = await client.initialize()
        if ok:
            await client.list_tools()

    async def list_all_tools(self) -> dict[str, list[dict]]:
        return {name: c._tools_cache for name, c in self._clients.items()}

    async def call(self, server: str, tool: str, args: dict | None = None) -> dict:
        client = self._clients.get(server)
        if not client:
            return {"error": f"unknown MCP server '{server}'",
                    "available": list(self._clients.keys())}
        return await client.call_tool(tool, args)

    async def health(self) -> dict:
        return {
            "servers": {name: await c.health() for name, c in self._clients.items()},
            "skipped": self._skipped,
            "loaded_at": self._loaded_at,
        }

    async def close(self) -> None:
        for c in self._clients.values():
            await c.close()


mcp_registry = MCPRegistry()
