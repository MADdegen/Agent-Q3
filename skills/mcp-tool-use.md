---
name: mcp-tool-use
description: Discover and call MCP tools via the bridge
triggers: [search reddit, weather, kite, browser, scrape page, polymarket, arxiv paper, wikipedia, search the web]
roles: [reasoner, coder, tandem, coder_dedicated]
---
The MCP Bridge (`http://mcp-bridge:8004`) is the single gateway to every configured MCP server.

Workflow:
1. List available tools: `GET /mcp/tools` — returns flat list across all servers.
2. Pick the right server + tool for the user's request:
   - Reddit content → `reddit-mcp`
   - Weather → `weather-mcp`
   - Trading / market data → `kite-trading-mcp`
   - Browser automation → `playwright-mcp` (stdio, may be unavailable in cloud-only mode)
   - Generic meta-search → `searxng-mcp`
   - Academic papers → `arxiv-mcp`
   - MCP discovery → `smithery-search`
3. Call it: `POST /mcp/call` with `{server, tool, args, cache_ttl_secs}`.
4. Set `cache_ttl_secs=300` for idempotent read-only calls (weather, paper lookups) — saves round-trips.
5. Never instantiate MCP clients directly from app services — always go through the bridge.
