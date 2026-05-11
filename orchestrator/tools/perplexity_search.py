"""
perplexity_search.py — Full Perplexity Sonar API integration.
Ported from perplexity-v.1/lib/tools/perplexity-search.ts.
Available to BOTH Reasoner (deep research) and Coder (doc lookup) agents.

Models:
  sonar                — fast, cheap,  127K ctx
  sonar-pro            — best quality, 200K ctx, search_context_size support
  sonar-reasoning      — thinking mode, 127K ctx
  sonar-reasoning-pro  — best reasoning + search, 127K ctx
  sonar-deep-research  — multi-step research, 128K ctx
"""
import httpx
import json
from typing import Literal, Optional
from orchestrator.config import settings

PPLX_MODELS = {
    "sonar":               {"ctx": 127_000, "cost_per_1k": 0.001, "supports_ctx_size": False},
    "sonar-pro":           {"ctx": 200_000, "cost_per_1k": 0.003, "supports_ctx_size": True},
    "sonar-reasoning":     {"ctx": 127_000, "cost_per_1k": 0.005, "supports_ctx_size": False},
    "sonar-reasoning-pro": {"ctx": 127_000, "cost_per_1k": 0.008, "supports_ctx_size": False},
    "sonar-deep-research": {"ctx": 128_000, "cost_per_1k": 0.015, "supports_ctx_size": False},
}

PplxModel = Literal[
    "sonar", "sonar-pro", "sonar-reasoning",
    "sonar-reasoning-pro", "sonar-deep-research"
]


async def perplexity_search(
    query: str,
    model: PplxModel = "sonar-pro",
    system_prompt: Optional[str] = None,
    conversation_history: Optional[list[dict]] = None,
    max_tokens: int = 2048,
    temperature: float = 0.2,
    return_images: bool = False,
    return_related_questions: bool = True,
    search_domain_filter: Optional[list[str]] = None,
    search_recency_filter: Optional[Literal["day","week","month","year"]] = None,
    search_context_size: Literal["low","medium","high"] = "medium",
) -> dict:
    """
    Call Perplexity Sonar API.  Used by:
      - Reasoner agent: deep research, current events, market analysis
      - Coder agent:    doc lookup, library references, Stack Overflow-style queries
    """
    api_key = settings.perplexity_api_key
    if not api_key:
        return {"error": "PERPLEXITY_API_KEY not configured", "query": query}

    messages: list[dict] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    if conversation_history:
        messages.extend(conversation_history)
    messages.append({"role": "user", "content": query})

    model_meta = PPLX_MODELS.get(model, PPLX_MODELS["sonar-pro"])

    payload: dict = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "return_citations": True,
        "return_images": return_images,
        "return_related_questions": return_related_questions,
    }
    if search_domain_filter:
        payload["search_domain_filter"] = search_domain_filter
    if search_recency_filter:
        payload["search_recency_filter"] = search_recency_filter
    if model_meta["supports_ctx_size"]:
        payload["web_search_options"] = {"search_context_size": search_context_size}

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        choice = data["choices"][0]
        answer = choice["message"]["content"]
        citations    = data.get("citations", [])
        images       = data.get("images", [])
        related_qs   = data.get("related_questions", [])
        usage        = data.get("usage", {})

        return {
            "answer":             answer,
            "citations":          citations,
            "images":             images,
            "related_questions":  related_qs,
            "model":              model,
            "usage":              usage,
            "cost_estimate_usd":  (usage.get("total_tokens", 0) / 1000) * model_meta["cost_per_1k"],
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"Perplexity API {e.response.status_code}: {e.response.text[:200]}", "query": query}
    except Exception as e:
        return {"error": str(e), "query": query}


# ── Convenience wrappers for common agent tasks ───────────────────────────────

async def deep_research(topic: str, recency: Optional[Literal["day","week","month","year"]] = None) -> dict:
    """Reasoner agent: multi-step deep research on a topic."""
    return await perplexity_search(
        query=topic,
        model="sonar-deep-research",
        system_prompt="You are an expert research analyst. Provide comprehensive, well-sourced analysis.",
        return_related_questions=True,
        search_recency_filter=recency,
        max_tokens=4096,
    )


async def doc_lookup(query: str, domains: Optional[list[str]] = None) -> dict:
    """Coder agent: look up technical documentation, API references, code examples."""
    return await perplexity_search(
        query=query,
        model="sonar-pro",
        system_prompt="You are a precise technical assistant. Return accurate documentation, code examples, and API references.",
        search_domain_filter=domains or ["docs.python.org", "developer.mozilla.org", "docs.github.com",
                                          "stackoverflow.com", "pypi.org", "npmjs.com"],
        search_context_size="high",
        max_tokens=2048,
    )
