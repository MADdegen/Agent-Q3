import httpx
import structlog
from orchestrator.config import settings

logger = structlog.get_logger(__name__)

async def call_runpod_community(model: str, prompt: str, endpoint: str) -> str:
    """Call RunPod Community Cloud Ollama endpoint"""
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                f"{endpoint}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "temperature": 0.7,
                }
            )
            if r.status_code == 200:
                result = r.json()
                return result.get("response", "")
            else:
                logger.error("runpod community error", status=r.status_code)
                raise Exception(f"RunPod Community error: {r.status_code}")
        except Exception as e:
            logger.error("runpod community call failed", error=str(e))
            raise

async def call_runpod_serverless(model: str, prompt: str, endpoint: str) -> str:
    """Call RunPod Serverless endpoint"""
    async with httpx.AsyncClient(timeout=300) as client:
        try:
            r = await client.post(
                f"{endpoint}",
                json={
                    "input": {
                        "model": model,
                        "prompt": prompt,
                        "temperature": 0.7,
                    }
                }
            )
            if r.status_code == 200:
                result = r.json()
                output = result.get("output", {})
                return output.get("response", "")
            else:
                logger.error("runpod serverless error", status=r.status_code)
                raise Exception(f"RunPod Serverless error: {r.status_code}")
        except Exception as e:
            logger.error("runpod serverless call failed", error=str(e))
            raise
