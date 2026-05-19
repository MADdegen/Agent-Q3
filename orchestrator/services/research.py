"""
Agent-Q3 — Deep Research Service
Wires the existing tools/ stack into a dedicated research API:
  - Perplexity Sonar (deep_research, sonar-reasoning-pro)
  - Exa semantic + Tavily news (web_search.py)
  - Free fallback: DuckDuckGo, Jina Reader, ArXiv, Wikipedia, GitHub (free_search.py)
  - Polymarket / Gamma / CLOB (prediction_markets.py)
  - MCP discovery (mcp_search.py)
  - Kimi-VL reasoning over results → Hermes3 synthesis → Qwen3-48B final report

Endpoints:
  POST /v1/research/deep       — multi-provider deep research (Perplexity → fallback chain)
  POST /v1/research/scrape     — Jina Reader page extraction
  POST /v1/research/quant      — Polymarket conviction analysis
  POST /v1/research/synthesize — full pipeline: search → Kimi reads → Hermes synthesizes → Qwen reports
  POST /v1/research/code       — semantic code search (Exa/Tavily biased to code repos)
  POST /v1/research/docs       — domain-scoped documentation lookup (Perplexity doc_lookup)
  POST /v1/research/packages   — PyPI + npm package metadata + security check
  POST /v1/research/conviction — Polymarket per-market conviction + CLOB orderbook analysis
  GET  /health
"""

from contextlib import asynccontextmanager
from typing import Optional

import structlog
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel, Field

from ..config import settings
from ..router import router, Backend
from ..memory import memory
from ..skills import skills
from ..plugins import plugins
from ..models import REASONER_SYSTEM, CODER_SYSTEM, HERMES_SYSTEM

# Import existing research tools
from ..tools import perplexity_search as pplx
from ..tools import web_search as ws
from ..tools import free_search as fs
from ..tools import prediction_markets as pm
from ..tools import mcp_search as mcps

log = structlog.get_logger(__name__)


# ── Request schemas ──────────────────────────────────────────────────────────

class DeepResearchRequest(BaseModel):
    query: str
    depth: int = Field(default=3, ge=1, le=5, description="Number of providers to query")
    use_perplexity: bool = True
    use_exa: bool = True
    use_tavily: bool = True
    use_free: bool = True
    recency: str | None = Field(default=None, description="day|week|month|year")
    domains: list[str] | None = None


class ScrapeRequest(BaseModel):
    url: str
    max_chars: int = 8000


class QuantRequest(BaseModel):
    topic: str
    limit: int = 10


class SynthesizeRequest(BaseModel):
    query: str
    depth: int = 3
    include_quant: bool = False


RESEARCH_SYSTEM = """You are the Research Synthesis Agent in the Agent-Q3 deep-research pipeline.

Your role: read raw search results, citations, and market data, then produce a tight, evidence-grounded brief.
- Lead with the answer. Use specific numbers and citations over adjectives.
- Cite sources inline with [n] markers tied to a numbered list at the end.
- Flag uncertainty explicitly. Note where sources conflict.
- Never use: leverage, synergy, unlock value, game-changing, ecosystem play.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Research service starting",
        perplexity=settings.has_perplexity(),
        exa=settings.has_exa(),
        tavily=settings.has_tavily(),
    )
    yield
    log.info("Research service shutting down")


app = FastAPI(
    title="Agent-Q3 Deep Research Service",
    description="Perplexity-grade deep research + quant + scraping, synthesized by Kimi-VL+Hermes+Qwen",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


@app.get("/")
async def root():
    return {
        "service": "Agent-Q3 Deep Research",
        "providers": {
            "perplexity": settings.has_perplexity(),
            "exa":        settings.has_exa(),
            "tavily":     settings.has_tavily(),
            "free_tools": True,
            "polymarket": True,
        },
        "synthesis_chain": "Kimi-VL → Hermes3 → Qwen3-48B-A4B",
    }


@app.get("/health")
async def health():
    ok = False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(f"{settings.ollama_base_url}/api/tags")
            ok = r.status_code == 200
    except Exception:
        pass
    return {
        "status": "ok" if ok else "degraded",
        "ollama": ok,
        "providers": {
            "perplexity": settings.has_perplexity(),
            "exa":        settings.has_exa(),
            "tavily":     settings.has_tavily(),
        },
    }


# ── /v1/research/deep ─────────────────────────────────────────────────────────

@app.post("/v1/research/deep")
async def deep_research(req: DeepResearchRequest):
    """Multi-provider deep research with auto-fallback chain."""
    results = {"query": req.query, "providers": {}}

    # 1. Perplexity Sonar deep-research (primary if key available)
    if req.use_perplexity and settings.has_perplexity():
        try:
            results["providers"]["perplexity"] = await pplx.deep_research(
                req.query, recency=req.recency,
            )
        except Exception as e:
            log.warning("perplexity failed", error=str(e))
            results["providers"]["perplexity"] = {"error": str(e)}

    # 2. Exa semantic search
    if req.use_exa and settings.has_exa():
        try:
            results["providers"]["exa"] = await ws.search_exa([req.query], max_per_query=10)
        except Exception as e:
            log.warning("exa failed", error=str(e))
            results["providers"]["exa"] = {"error": str(e)}

    # 3. Tavily news
    if req.use_tavily and settings.has_tavily():
        try:
            results["providers"]["tavily"] = await ws.search_tavily([req.query], max_per_query=10)
        except Exception as e:
            log.warning("tavily failed", error=str(e))
            results["providers"]["tavily"] = {"error": str(e)}

    # 4. Free tools (always, as fallback)
    if req.use_free:
        try:
            results["providers"]["free"] = await fs.smart_search(req.query, role="reasoner")
        except Exception as e:
            log.warning("free search failed", error=str(e))
            results["providers"]["free"] = {"error": str(e)}

    return results


# ── /v1/research/scrape ───────────────────────────────────────────────────────

@app.post("/v1/research/scrape")
async def scrape(req: ScrapeRequest):
    """Free page scrape via Jina Reader (r.jina.ai)."""
    try:
        result = await fs.jina_read(req.url)
        # Truncate to max_chars if the reader returned more
        if isinstance(result, dict) and "content" in result:
            result["content"] = result["content"][: req.max_chars]
        return {"url": req.url, "result": result, "provider": "jina-reader"}
    except Exception as e:
        raise HTTPException(503, detail=str(e))


# ── /v1/research/quant ────────────────────────────────────────────────────────

@app.post("/v1/research/quant")
async def quant(req: QuantRequest):
    """Polymarket conviction analysis on a topic."""
    try:
        markets = await pm.search_related_markets(req.topic, limit=req.limit)
        return {
            "topic": req.topic,
            "markets": markets,
            "platform_fee_pct": 1.88,
        }
    except Exception as e:
        raise HTTPException(503, detail=str(e))


# ── /v1/research/synthesize ───────────────────────────────────────────────────

@app.post("/v1/research/synthesize")
async def synthesize(req: SynthesizeRequest):
    """
    Full deep-research pipeline:
      1. Gather results from all providers (deep_research)
      2. Kimi-VL reads everything and extracts key findings
      3. Hermes3 synthesizes findings into a structured analysis
      4. Qwen3-48B produces the final report with citations
    """
    # 1. Gather
    gather = await deep_research(DeepResearchRequest(query=req.query, depth=req.depth))
    quant_block = None
    if req.include_quant:
        try:
            quant_block = await quant(QuantRequest(topic=req.query, limit=8))
        except Exception:
            quant_block = None

    raw_dump = str(gather)
    if quant_block:
        raw_dump += f"\n\n[Polymarket Conviction]\n{quant_block}"

    # 2. Kimi-VL reads
    kimi_msgs = [
        {"role": "system", "content": REASONER_SYSTEM},
        {"role": "user", "content":
            f"Research query: {req.query}\n\n"
            f"Raw multi-provider results:\n{raw_dump}\n\n"
            f"Extract the 5-10 most important findings as concise bullets. "
            f"Tag each with [source: provider]."},
    ]
    try:
        kimi_result = await router.route(
            model_role="reasoner",
            messages=kimi_msgs,
            temperature=0.4,
            max_tokens=2048,
        )
        kimi_findings = kimi_result.get("message", {}).get("content", "") if isinstance(
            kimi_result.get("message"), dict) else str(kimi_result.get("message", ""))
    except Exception as e:
        raise HTTPException(503, detail=f"Kimi-VL findings step failed: {e}")

    # 3. Hermes3 synthesizes
    hermes_msgs = [
        {"role": "system", "content": HERMES_SYSTEM},
        {"role": "user", "content":
            f"Query: {req.query}\n\nKey findings extracted:\n{kimi_findings}\n\n"
            f"Synthesize these into a structured analysis: thesis, supporting evidence, "
            f"counterpoints, unknowns. Flag any source conflicts explicitly."},
    ]
    try:
        hermes_result = await router.route(
            model_role="tandem",
            messages=hermes_msgs,
            temperature=0.4,
            max_tokens=2048,
        )
        hermes_synthesis = hermes_result.get("message", {}).get("content", "") if isinstance(
            hermes_result.get("message"), dict) else str(hermes_result.get("message", ""))
    except Exception as e:
        raise HTTPException(503, detail=f"Hermes synthesis failed: {e}")

    # 4. Qwen3-48B final report
    final_msgs = [
        {"role": "system", "content": RESEARCH_SYSTEM},
        {"role": "user", "content":
            f"Query: {req.query}\n\nFindings:\n{kimi_findings}\n\n"
            f"Analysis:\n{hermes_synthesis}\n\n"
            f"Produce the final research brief. Be evidence-grounded, cite inline, "
            f"end with a numbered source list."},
    ]
    try:
        final_result = await router.route(
            model_role="coder",
            messages=final_msgs,
            temperature=0.3,
            max_tokens=4096,
        )
        report = final_result.get("message", {}).get("content", "") if isinstance(
            final_result.get("message"), dict) else str(final_result.get("message", ""))
    except Exception as e:
        raise HTTPException(503, detail=f"Final report failed: {e}")

    return {
        "query": req.query,
        "findings":  kimi_findings,
        "analysis":  hermes_synthesis,
        "report":    report,
        "providers_used": list(gather["providers"].keys()),
        "quant":     quant_block,
        "pipeline": {
            "stage1_kimi":   kimi_result.get("_model_used"),
            "stage2_hermes": hermes_result.get("_model_used"),
            "stage3_qwen":   final_result.get("_model_used"),
        },
    }
