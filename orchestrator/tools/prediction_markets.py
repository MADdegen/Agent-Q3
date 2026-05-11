"""
prediction_markets.py — Polymarket + MAD Gambit market intelligence.
Ported and adapted from MADdegen/agents/polymarket/{polymarket.py,gamma.py}.
Used by Reasoner agent for market analysis, sentiment, and conviction scoring.
"""
import httpx
from typing import Optional


GAMMA_URL  = "https://gamma-api.polymarket.com"
CLOB_URL   = "https://clob.polymarket.com"


# ── Market data fetchers ──────────────────────────────────────────────────────

async def get_polymarket_markets(
    limit: int = 20,
    active: bool = True,
    query: Optional[str] = None,
    tag: Optional[str] = None,
) -> list[dict]:
    """
    Fetch active Polymarket markets via Gamma API.
    Reasoner uses this for market intelligence + conviction analysis.
    """
    params: dict = {"limit": limit}
    if active:
        params["active"] = "true"
        params["closed"] = "false"
    if query:
        params["_c"] = query
    if tag:
        params["tag"] = tag

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GAMMA_URL}/markets", params=params)
        if r.status_code == 200:
            markets = r.json()
            return [_parse_market(m) for m in markets[:limit]]
        return []


async def get_polymarket_events(
    limit: int = 10,
    active: bool = True,
    tag: Optional[str] = None,
) -> list[dict]:
    """Fetch market events with tag filtering."""
    params: dict = {"limit": limit}
    if active:
        params["active"] = "true"
    if tag:
        params["tag"] = tag

    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(f"{GAMMA_URL}/events", params=params)
        if r.status_code == 200:
            return r.json()[:limit]
        return []


async def get_market_orderbook(token_id: str) -> dict:
    """Fetch CLOB order book for a specific market token."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{CLOB_URL}/book", params={"token_id": token_id})
        if r.status_code == 200:
            return r.json()
        return {}


def _parse_market(m: dict) -> dict:
    """Normalize market response — extract conviction-relevant fields."""
    outcomes = []
    try:
        import json as _json
        prices = _json.loads(m.get("outcomePrices", "[]")) if isinstance(m.get("outcomePrices"), str) else m.get("outcomePrices", [])
        token_ids = _json.loads(m.get("clobTokenIds", "[]")) if isinstance(m.get("clobTokenIds"), str) else m.get("clobTokenIds", [])
        outcome_names = m.get("outcomes", "[]")
        if isinstance(outcome_names, str):
            outcome_names = _json.loads(outcome_names)
        for i, name in enumerate(outcome_names):
            outcomes.append({
                "name":     name,
                "price":    float(prices[i]) if i < len(prices) else None,
                "token_id": token_ids[i] if i < len(token_ids) else None,
            })
    except Exception:
        pass

    return {
        "id":           m.get("id"),
        "question":     m.get("question"),
        "description":  m.get("description","")[:200],
        "end_date":     m.get("endDate"),
        "volume":       m.get("volume"),
        "liquidity":    m.get("liquidity"),
        "active":       m.get("active"),
        "outcomes":     outcomes,
        "tags":         [t.get("label","") for t in m.get("tags", [])],
        "clob_rewards": m.get("clobRewards"),
        "source":       "polymarket",
    }


# ── Conviction analysis (Reasoner agent) ─────────────────────────────────────

async def analyze_market_conviction(market_id: str) -> dict:
    """
    Pull market data + order book → return conviction metrics.
    Used by Reasoner to inform MAD Gambit market resolution scoring.
    """
    markets = await get_polymarket_markets(limit=50)
    target = next((m for m in markets if m.get("id") == market_id), None)
    if not target:
        return {"error": f"Market {market_id} not found"}

    outcomes = target.get("outcomes", [])
    conviction_scores = []
    for outcome in outcomes:
        price = outcome.get("price")
        if price is not None:
            # Implied probability = market price (0–1)
            implied_prob = float(price)
            # Conviction score: distance from 0.5 (the more decisive, the higher)
            conviction = abs(implied_prob - 0.5) * 2  # 0=coin-flip, 1=certain
            conviction_scores.append({
                "outcome":      outcome["name"],
                "implied_prob": round(implied_prob, 4),
                "conviction":   round(conviction, 4),
                "token_id":     outcome.get("token_id"),
            })

    return {
        "market_id":    market_id,
        "question":     target.get("question"),
        "volume":       target.get("volume"),
        "liquidity":    target.get("liquidity"),
        "convictions":  conviction_scores,
        "platform":     "polymarket",
        "mad_gambit_fee": "1.88%",  # canonical platform fee
    }


async def search_related_markets(topic: str, limit: int = 10) -> list[dict]:
    """Find Polymarket markets related to a research topic."""
    return await get_polymarket_markets(limit=limit, query=topic)
