"""RunPod Serverless provider for Agent-Q3.

Submits jobs to a RunPod serverless endpoint that exposes an
Ollama-compatible handler, then polls for completion.
"""
from __future__ import annotations

import asyncio
from typing import Optional

import httpx
import structlog

from ..config import settings

logger = structlog.get_logger(__name__)

_POLL_INTERVAL_SECS: float = 1.5
_MAX_POLL_ATTEMPTS: int = 120  # 3 minutes at 1.5 s intervals


class RunPodProvider:
    """Wraps the RunPod Serverless REST API with async job polling."""

    BASE_URL: str = "https://api.runpod.io/v2"

    def __init__(self, timeout: float = 30.0) -> None:
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not settings.runpod_api_key:
            raise RuntimeError("RUNPOD_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {settings.runpod_api_key}",
            "Content-Type": "application/json",
        }

    async def _submit_job(
        self,
        client: httpx.AsyncClient,
        endpoint_id: str,
        payload: dict,
    ) -> str:
        """Submit a job and return the job ID."""
        r = await client.post(
            f"{self.BASE_URL}/{endpoint_id}/run",
            headers=self._headers(),
            json={"input": payload},
        )
        r.raise_for_status()
        job_id: str = r.json()["id"]
        logger.debug("runpod job submitted", endpoint=endpoint_id, job_id=job_id)
        return job_id

    async def _poll_job(
        self,
        client: httpx.AsyncClient,
        endpoint_id: str,
        job_id: str,
    ) -> dict:
        """Poll until the job completes and return the output dict."""
        for attempt in range(_MAX_POLL_ATTEMPTS):
            await asyncio.sleep(_POLL_INTERVAL_SECS)
            r = await client.get(
                f"{self.BASE_URL}/{endpoint_id}/status/{job_id}",
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
            status = data.get("status", "")

            if status == "COMPLETED":
                logger.info("runpod job completed", job_id=job_id, attempts=attempt + 1)
                return data.get("output", {})
            if status in ("FAILED", "CANCELLED", "TIMED_OUT"):
                logger.error("runpod job failed", job_id=job_id, status=status)
                raise RuntimeError(f"RunPod job {job_id} ended with status={status}")

        raise TimeoutError(f"RunPod job {job_id} did not complete within the polling window")

    async def generate(
        self,
        endpoint_id: str,
        model: str,
        messages: list[dict],
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs: object,
    ) -> dict:
        """Submit an inference job and wait for the result.

        Returns an Ollama-style response envelope.
        """
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            **kwargs,
        }

        logger.debug("runpod generate", endpoint=endpoint_id, model=model)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                job_id = await self._submit_job(client, endpoint_id, payload)
                output = await self._poll_job(client, endpoint_id, job_id)

            message = output.get("message", {"role": "assistant", "content": str(output)})
            return {
                "message": message,
                "model": model,
                "provider": "runpod",
                "runpod_job_id": job_id,
            }
        except Exception as exc:
            logger.error("runpod generate failed", endpoint=endpoint_id, error=str(exc))
            raise

    async def runsync(
        self,
        endpoint_id: str,
        model: str,
        messages: list[dict],
        **kwargs: object,
    ) -> dict:
        """Use the /runsync endpoint for short-lived jobs (< 90 s)."""
        payload = {
            "model": model,
            "messages": messages,
            **kwargs,
        }

        logger.debug("runpod runsync", endpoint=endpoint_id, model=model)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    f"{self.BASE_URL}/{endpoint_id}/runsync",
                    headers=self._headers(),
                    json={"input": payload},
                )
                r.raise_for_status()
                data = r.json()

            output = data.get("output", {})
            message = output.get("message", {"role": "assistant", "content": str(output)})
            return {
                "message": message,
                "model": model,
                "provider": "runpod",
                "runpod_job_id": data.get("id"),
            }
        except Exception as exc:
            logger.error("runpod runsync failed", endpoint=endpoint_id, error=str(exc))
            raise

    async def health_check(self, endpoint_id: Optional[str] = None) -> bool:
        """Check whether the RunPod endpoint is reachable."""
        ep = endpoint_id or settings.runpod_endpoint_id
        if not ep:
            return False
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    f"{self.BASE_URL}/{ep}/health",
                    headers=self._headers(),
                )
            return r.status_code == 200
        except Exception:
            return False
