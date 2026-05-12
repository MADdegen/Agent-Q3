"""OpenRouter API provider — Tier 4 guaranteed fallback for Agent-Q3."""
import httpx
import structlog

from orchestrator.config import settings

logger = structlog.get_logger(__name__)


async def call_openrouter(model: str, prompt: str, max_tokens: int = 2048) -> str:
    """Call OpenRouter API as guaranteed fallback."""
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openrouter_api_key}",
                    "HTTP-Referer": "https://agent-q3.railway.app",
                    "X-Title": "Agent-Q3",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                },
            )
            if r.status_code == 200:
                result = r.json()
                content = result["choices"][0]["message"]["content"]
                logger.info("openrouter response ok", model=model, chars=len(content))
                return content
            else:
                logger.error(
                    "openrouter api error",
                    status=r.status_code,
                    body=r.text[:200],
                )
                raise Exception(f"OpenRouter API error: {r.status_code}")
        except Exception as e:
            logger.error("openrouter call failed", error=str(e))
            raise
