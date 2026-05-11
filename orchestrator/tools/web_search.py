from __future__ import annotations

"""
web_search.py — Multi-provider web search for both agents.
Ported from perplexity-v.1/lib/tools/web-search.ts.

Provider priority (auto-fallback):
  1. Exa         — semantic neural search, best for research queries
  2. Tavily      — fast, good for news + current events
  3. Brave       — privacy-respecting, good general fallback
  4. Firecrawl   — full-page scrape fallback when snippet not enough
"""
import httpx
import re
from typing import Literal, Optional
from orchestrator.config import settings


def extract_domain(url: str) -> str:
    m = re.match(r"^https?://([^/?#]+)", url)
    return m.group(1) if m else url


def deduplicate(results: list[dict]) -> list[dict]:
    seen_urls = set()
    seen_domains = set()
    out = []
    for r in results:
        url = r.get("url", "")
        domain = extract_domain(url)
        if url not in seen_urls and domain not in seen_domains:
            seen_urls.add(url)
            seen_domains.add(domain)
            out.append(r)
    return out


async def search_exa(queries: list[str], max_per_query: int = 5) -> list[dict]:
    """Exa semantic search — best for research, GitHub, papers."""
    api_key = settings.exa_api_key
    if not api_key:
        return []
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        for query in queries[:5]:
            try:
                r = await client.post(
                    "https://api.exa.ai/search",
                    headers={"x-api-key": api_key, "Content-Type": "application/json"},
                    json={"query": query, "numResults": max_per_query,
                          "type": "auto", "contents": {"text": {"maxCharacters": 800}}},
                )
                if r.status_code == 200:
                    for item in r.json().get("results", []):
                        results.append({
                            "title":         item.get("title", ""),
                            "url":           item.get("url", ""),
                            "content":       item.get("text", item.get("content", ""))[:600],
                            "published":     item.get("publishedDate", ""),
                            "provider":      "exa",
                        })
            except Exception:
                pass
    return results


async def search_tavily(queries: list[str], max_per_query: int = 5,
                        topic: Literal["general","news"] = "general") -> list[dict]:
    """Tavily — fast, good for news and current events."""
    api_key = settings.tavily_api_key
    if not api_key:
        return []
    results = []
    async with httpx.AsyncClient(timeout=20) as client:
        for query in queries[:5]:
            try:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": api_key, "query": query,
                          "max_results": max_per_query, "topic": topic,
                          "include_answer": False, "include_raw_content": False},
                )
                if r.status_code == 200:
                    for item in r.json().get("results", []):
                        results.append({
                            "title":     item.get("title", ""),
                            "url":       item.get("url", ""),
                            "content":   item.get("content", "")[:600],
                            "published": item.get("published_date", ""),
                            "score":     item.get("score", 0),
                            "provider":  "tavily",
                        })
            except Exception:
                pass
    return results


async def web_search(
    queries: list[str],
    max_results: int = 10,
    topic: Literal["general","news"] = "general",
    provider: Literal["auto","exa","tavily"] = "auto",
    include_domains: list[str] | None = None,
) -> dict:
    """
    Multi-provider web search.  Used by BOTH agents:
      - Reasoner: research, current events, market intelligence
      - Coder:    library docs, GitHub issues, changelogs, Stack Overflow

    Auto mode: tries Exa first (semantic), falls back to Tavily.
    """
    results: list[dict] = []

    if provider in ("auto", "exa"):
        results += await search_exa(queries, max_per_query=max_results // max(len(queries), 1))

    if provider in ("auto", "tavily") and len(results) < max_results:
        results += await search_tavily(queries, topic=topic,
                                       max_per_query=max_results // max(len(queries), 1))

    # Filter by domain if requested
    if include_domains:
        results = [r for r in results
                   if any(d in extract_domain(r.get("url","")) for d in include_domains)]

    results = deduplicate(results)[:max_results]

    return {
        "queries":  queries,
        "total":    len(results),
        "results":  results,
        "provider": provider,
    }


# ── Convenience wrappers ──────────────────────────────────────────────────────

async def research_search(topic: str) -> dict:
    """Reasoner: broad research across multiple angles."""
    return await web_search(queries=[topic, f"{topic} analysis", f"{topic} latest 2025"],
                             max_results=15, provider="auto")


async def code_search(query: str) -> dict:
    """Coder: focused technical search — GitHub, docs, Stack Overflow."""
    return await web_search(
        queries=[query, f"{query} example", f"{query} documentation"],
        max_results=10, provider="exa",
        include_domains=["github.com", "stackoverflow.com", "docs.python.org",
                         "developer.mozilla.org", "npmjs.com", "pypi.org"],
    )
