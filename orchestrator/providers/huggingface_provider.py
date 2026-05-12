"""HuggingFace Inference API provider for Agent-Q3."""
import httpx
import structlog

from orchestrator.config import settings

logger = structlog.get_logger(__name__)

# Rotate through up to 3 HF tokens to avoid 429s
_HF_TOKENS = [t for t in [settings.hf_token, settings.hf_token_2, settings.hf_token_3] if t]
_token_index = 0


def _next_token() -> str:
    global _token_index
    if not _HF_TOKENS:
        raise RuntimeError("No HuggingFace tokens configured")
    token = _HF_TOKENS[_token_index % len(_HF_TOKENS)]
    _token_index += 1
    return token


async def call_huggingface(model_id: str, prompt: str, max_tokens: int = 2048) -> str:
    """Call HuggingFace Inference API (text-generation endpoint)."""
    token = _next_token()
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                f"https://api-inference.huggingface.co/models/{model_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": max_tokens,
                        "temperature": 0.7,
                        "return_full_text": False,
                    },
                },
            )
            if r.status_code == 200:
                raw = r.json()
                text = (
                    raw[0]["generated_text"]
                    if isinstance(raw, list)
                    else raw.get("generated_text", "")
                )
                logger.info("huggingface response ok", model=model_id, chars=len(text))
                return text
            else:
                logger.error(
                    "huggingface api error",
                    status=r.status_code,
                    body=r.text[:200],
                )
                raise Exception(f"HuggingFace API error: {r.status_code}")
        except Exception as e:
            logger.error("huggingface call failed", error=str(e))
            raise
