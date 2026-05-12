"""HuggingFace Inference API provider for Agent-Q3.

Supports multi-token rotation (up to 3 tokens) to work around
per-token rate limits on the free inference tier.
"""
from __future__ import annotations

import itertools
from typing import Optional

import httpx
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)

# Token pool — rotate across up to 3 HF tokens to spread rate-limit pressure
_TOKEN_POOL = [t for t in [settings.hf_token, settings.hf_token_2, settings.hf_token_3] if t]
_token_cycle = itertools.cycle(_TOKEN_POOL) if _TOKEN_POOL else None


def _next_token() -> str:
    """Return the next HF token from the rotation pool."""
    if _token_cycle is None:
        raise RuntimeError("No HuggingFace tokens configured (HF_TOKEN / HF_TOKEN_2 / HF_TOKEN_3)")
    return next(_token_cycle)


class HuggingFaceProvider:
    """Wraps the HuggingFace Inference API with token rotation and retries."""

    BASE_URL: str = "https://api-inference.huggingface.co/models"

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout

    async def generate(
        self,
        model_id: str,
        messages: list[dict],
        max_new_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: object,
    ) -> dict:
        """Call the HuggingFace text-generation endpoint.

        Normalises the response to the Ollama-style envelope used by the
        rest of the orchestrator so callers don't need provider-specific
        handling.
        """
        token = _next_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": messages[-1]["content"],
            "parameters": {
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
                "return_full_text": False,
                **{k: v for k, v in kwargs.items() if k not in ("max_tokens",)},
            },
        }

        logger.debug("hf request", model=model_id, tokens_in_pool=len(_TOKEN_POOL))

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.BASE_URL}/{model_id}",
                    headers=headers,
                    json=payload,
                )
                r.raise_for_status()
                raw = r.json()

            # HF returns a list for text-generation models
            text: str
            if isinstance(raw, list):
                text = raw[0].get("generated_text", "")
            else:
                text = raw.get("generated_text", "")

            logger.info("hf response ok", model=model_id, chars=len(text))
            return {
                "message": {"role": "assistant", "content": text},
                "model": model_id,
                "provider": "huggingface",
            }
        except httpx.HTTPStatusError as exc:
            logger.error(
                "hf http error",
                model=model_id,
                status=exc.response.status_code,
                body=exc.response.text[:200],
            )
            raise
        except Exception as exc:
            logger.error("hf request failed", model=model_id, error=str(exc))
            raise

    async def health_check(self, model_id: Optional[str] = None) -> bool:
        """Ping the HF API to verify the token is valid."""
        probe = model_id or settings.hf_support_model
        try:
            token = _next_token()
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"https://api-inference.huggingface.co/models/{probe}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            return r.status_code in (200, 503)  # 503 = model loading, still reachable
        except Exception:
            return False
