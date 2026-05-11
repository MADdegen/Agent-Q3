"""
mcp_search.py — MCP server discovery for both Reasoner + Coder agents.
Ported from perplexity-v.1/lib/tools/mcp-search.ts (Smithery API).
Also scans Glama registry as secondary source.
"""
import httpx
from typing import Optional
from orchestrator.config import settings


async def search_mcp_servers(query: str, limit: int = 10) -> dict:
    """
    Search Smithery MCP registry + Glama for relevant MCP servers.
    Used by both agents for dynamic tool discovery at inference time.
    """
    results: list[dict] = []
    errors: list[str] = []

    # ── Smithery registry (primary) ──────────────────────────────────────────
    smithery_key = settings.smithery_api_key
    if smithery_key:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://registry.smithery.ai/servers",
                    params={"q": query, "limit": limit},
                    headers={"Authorization": f"Bearer {smithery_key}",
                             "Content-Type": "application/json"},
                )
                if r.status_code == 200:
                    data = r.json()
                    servers = data.get("servers", [])
                    # Enrich with deployment details
                    for srv in servers[:8]:
                        qname = srv.get("qualifiedName", "")
                        if qname:
                            try:
                                dr = await client.get(
                                    f"https://registry.smithery.ai/servers/{httpx.URL(qname)}",
                                    headers={"Authorization": f"Bearer {smithery_key}"},
                                )
                                if dr.status_code == 200:
                                    details = dr.json()
                                    srv["deploymentUrl"] = details.get("deploymentUrl")
                                    srv["connections"] = details.get("connections", [])
                            except Exception:
                                pass
                        results.append({
                            "source": "smithery",
                            "name": srv.get("displayName", srv.get("qualifiedName", "?")),
                            "qualified_name": qname,
                            "description": srv.get("description", "")[:120],
                            "deployment_url": srv.get("deploymentUrl"),
                            "connections": srv.get("connections", []),
                        })
        except Exception as e:
            errors.append(f"Smithery: {e}")

    # ── Glama registry (secondary) ────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://glama.ai/api/mcp/v1/servers",
                params={"limit": 10, "sort": "recent", "q": query},
                headers={"Accept": "application/json"},
            )
            if r.status_code == 200:
                data = r.json()
                servers = data.get("servers", data) if isinstance(data, dict) else data
                if isinstance(servers, list):
                    for s in servers[:8]:
                        results.append({
                            "source": "glama",
                            "name": s.get("name", "?"),
                            "description": s.get("description", "")[:120],
                            "url": s.get("url", s.get("githubUrl", "")),
                        })
    except Exception as e:
        errors.append(f"Glama: {e}")

    return {
        "query": query,
        "total": len(results),
        "results": results,
        "errors": errors if errors else None,
    }
