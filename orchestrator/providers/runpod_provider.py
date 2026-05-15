"""RunPod Community Cloud and Serverless providers for Agent-Q3."""
import httpx
import structlog

from orchestrator.config import settings

logger = structlog.get_logger(__name__)


async def call_runpod_community(model: str, prompt: str, base_url: str) -> str:
    """Call a RunPod Community Cloud node via Ollama-compatible API."""
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(
                f"{base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                },
            )
            if r.status_code == 200:
                data = r.json()
                content = data.get("message", {}).get("content", "")
                logger.info(
                    "runpod community response ok",
                    model=model,
                    endpoint=base_url,
                    chars=len(content),
                )
                return content
            else:
                logger.error(
                    "runpod community api error",
                    status=r.status_code,
                    body=r.text[:200],
                    endpoint=base_url,
                )
                raise Exception(f"RunPod Community API error: {r.status_code}")
        except Exception as e:
            logger.error("runpod community call failed", error=str(e), endpoint=base_url)
            raise


async def call_runpod_serverless(model: str, prompt: str, endpoint_url: str) -> str:
    """Call a RunPod Serverless endpoint (runsync, Ollama-compatible handler)."""
    if not settings.runpod_api_key:
        raise RuntimeError("RUNPOD_API_KEY not configured")
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            r = await client.post(
                f"{endpoint_url}/runsync",
                headers={
                    "Authorization": f"Bearer {settings.runpod_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "input": {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                    }
                },
            )
            if r.status_code == 200:
                data = r.json()
                output = data.get("output", {})
                content = (
                    output.get("message", {}).get("content", "")
                    if isinstance(output, dict)
                    else str(output)
                )
                logger.info(
                    "runpod serverless response ok",
                    model=model,
                    endpoint=endpoint_url,
                    chars=len(content),
                )
                return content
            else:
                logger.error(
                    "runpod serverless api error",
                    status=r.status_code,
                    body=r.text[:200],
                    endpoint=endpoint_url,
                )
                raise Exception(f"RunPod Serverless API error: {r.status_code}")
        except Exception as e:
            logger.error("runpod serverless call failed", error=str(e), endpoint=endpoint_url)
            raise
