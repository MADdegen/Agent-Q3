import httpx
import structlog
from orchestrator.config import settings

logger = structlog.get_logger(__name__)

async def call_huggingface(model: str, prompt: str, max_tokens: int = 512) -> str:
    """Call HuggingFace Inference API directly"""
    async with httpx.AsyncClient(timeout=60) as client:
        try:
            r = await client.post(
                f"https://api-inference.huggingface.co/models/{model}",
                headers={"Authorization": f"Bearer {settings.huggingface_api_token}"},
                json={
                    "inputs": prompt,
                    "parameters": {
                        "max_new_tokens": max_tokens,
                        "temperature": 0.7,
                        "top_p": 0.95,
                    }
                }
            )
            if r.status_code == 200:
                result = r.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get("generated_text", "")
                return str(result)
            else:
                logger.error("huggingface api error", status=r.status_code, body=r.text)
                raise Exception(f"HF API error: {r.status_code}")
        except Exception as e:
            logger.error("huggingface call failed", error=str(e))
            raise
