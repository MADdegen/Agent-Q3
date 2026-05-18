"""
Compute Router — Agent-Q3
Alternates between: Local Ollama → HuggingFace Inference → RunPod Serverless
Strategy: weighted round-robin with live health fallback
"""

import time
from enum import Enum
from typing import Optional
import httpx
import structlog

from .config import settings

log = structlog.get_logger(__name__)


class Backend(str, Enum):
    LOCAL    = "local"
    HF       = "huggingface"
    RUNPOD   = "runpod"


class BackendHealth:
    def __init__(self):
        self.healthy: bool = True
        self.last_check: float = 0
        self.queue_depth: int = 0
        self.consecutive_errors: int = 0
        self.check_interval_secs: int = 15

    def mark_error(self):
        self.consecutive_errors += 1
        if self.consecutive_errors >= 3:
            self.healthy = False
            log.warning("backend marked unhealthy", errors=self.consecutive_errors)

    def mark_success(self):
        self.consecutive_errors = 0
        self.healthy = True

    def needs_recheck(self) -> bool:
        return time.time() - self.last_check > self.check_interval_secs


class ComputeRouter:
    """
    Routes inference requests across Local / HuggingFace / RunPod.
    
    Weighted round-robin by default (60/25/15 split).
    Falls back gracefully if a backend is unhealthy or overloaded.
    """

    def __init__(self):
        self._health: dict[Backend, BackendHealth] = {
            Backend.LOCAL:   BackendHealth(),
            Backend.HF:      BackendHealth(),
            Backend.RUNPOD:  BackendHealth(),
        }
        self._rr_counter: int = 0
        self._weights = {
            Backend.LOCAL:   settings.local_weight,
            Backend.HF:      settings.hf_weight,
            Backend.RUNPOD:  settings.runpod_weight,
        }
        # Build weighted list for O(1) round-robin selection
        self._weighted_order: list[Backend] = self._build_weighted_order()

    def _build_weighted_order(self) -> list[Backend]:
        order = []
        for backend, weight in self._weights.items():
            order.extend([backend] * weight)
        return order

    def _next_backend(self) -> Backend:
        """Pick next backend via weighted round-robin, skipping unhealthy ones."""
        total = len(self._weighted_order)
        for _ in range(total):
            candidate = self._weighted_order[self._rr_counter % total]
            self._rr_counter += 1
            if self._health[candidate].healthy:
                return candidate
        # All unhealthy → force local
        log.warning("all backends unhealthy, forcing local")
        return Backend.LOCAL

    async def check_local_health(self) -> bool:
        h = self._health[Backend.LOCAL]
        if not h.needs_recheck():
            return h.healthy
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{settings.ollama_base_url}/api/tags")
                h.healthy = r.status_code == 200
                h.last_check = time.time()
                return h.healthy
        except Exception:
            h.healthy = False
            return False

    def select_backend(self, force: Backend | None = None) -> Backend:
        if force:
            return force
        if settings.compute_strategy == "local_first":
            return Backend.LOCAL if self._health[Backend.LOCAL].healthy else Backend.HF
        if settings.compute_strategy == "hf_first":
            return Backend.HF if self._health[Backend.HF].healthy else Backend.LOCAL
        if settings.compute_strategy == "runpod_first":
            return Backend.RUNPOD if self._health[Backend.RUNPOD].healthy else Backend.LOCAL
        # Default: round_robin / load_based
        return self._next_backend()

    # ── Backend implementations ───────────────────────────────────────────────

    async def call_local(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs
    ) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream,
            **kwargs
        }
        h = self._health[Backend.LOCAL]
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_secs
            ) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload
                )
                r.raise_for_status()
                h.mark_success()
                return r.json()
        except Exception as e:
            h.mark_error()
            log.error("local backend error", error=str(e))
            raise

    async def call_hf(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """HuggingFace Router — OpenAI-compatible chat completions endpoint."""
        token = settings.active_hf_token()
        if not token:
            raise RuntimeError("HF_TOKEN not configured")
        h = self._health[Backend.HF]
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model_id,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_secs
            ) as client:
                r = await client.post(
                    f"{settings.hf_router_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                r.raise_for_status()
                h.mark_success()
                raw = r.json()
                # Normalise OpenAI-format response → Ollama-style
                text = raw["choices"][0]["message"]["content"]
                return {
                    "message": {"role": "assistant", "content": text},
                    "backend": Backend.HF,
                    "model": model_id,
                    "usage": raw.get("usage"),
                }
        except Exception as e:
            h.mark_error()
            log.error("HF backend error", error=str(e))
            raise

    async def call_runpod(
        self,
        endpoint_id: str,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """RunPod serverless endpoint — expects an Ollama-compatible handler."""
        if not settings.runpod_api_key:
            raise RuntimeError("RUNPOD_API_KEY not configured")
        h = self._health[Backend.RUNPOD]
        headers = {
            "Authorization": f"Bearer {settings.runpod_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "input": {
                "model": model,
                "messages": messages,
                **kwargs
            }
        }
        try:
            async with httpx.AsyncClient(
                timeout=settings.request_timeout_secs
            ) as client:
                # Submit job
                r = await client.post(
                    f"{settings.runpod_api_url}/{endpoint_id}/runsync",
                    headers=headers,
                    json=payload
                )
                r.raise_for_status()
                h.mark_success()
                data = r.json()
                output = data.get("output", {})
                return {
                    "message": output.get("message", {"role": "assistant", "content": output}),
                    "backend": Backend.RUNPOD,
                    "model": model,
                    "runpod_job_id": data.get("id"),
                }
        except Exception as e:
            h.mark_error()
            log.error("RunPod backend error", error=str(e))
            raise

    async def route(
        self,
        model_role: str,           # "reasoner" | "coder"
        messages: list[dict],
        force_backend: Backend | None = None,
        **kwargs
    ) -> dict:
        """
        Main routing entry point.
        Selects backend, maps model_role → correct model ID per backend.
        Falls back through chain on failure.
        """
        backend = self.select_backend(force_backend)

        # Model IDs per role per backend
        model_map = {
            "reasoner": {
                Backend.LOCAL:  settings.reasoner_model,
                Backend.HF:     settings.hf_reasoner_model,
                Backend.RUNPOD: settings.reasoner_model,
            },
            "coder": {
                Backend.LOCAL:  settings.coder_model,
                Backend.HF:     settings.hf_coder_model,
                Backend.RUNPOD: settings.coder_model,
            },
        }
        model = model_map[model_role][backend]

        log.info("routing request", backend=backend, model=model, role=model_role)

        fallback_chain = [backend]
        for b in [Backend.LOCAL, Backend.HF, Backend.RUNPOD]:
            if b not in fallback_chain:
                fallback_chain.append(b)

        last_err = None
        for attempt_backend in fallback_chain:
            attempt_model = model_map[model_role][attempt_backend]
            try:
                if attempt_backend == Backend.LOCAL:
                    result = await self.call_local(attempt_model, messages, **kwargs)
                elif attempt_backend == Backend.HF:
                    result = await self.call_hf(attempt_model, messages, **kwargs)
                else:
                    ep_id = (
                        settings.runpod_reasoner_endpoint_id
                        if model_role == "reasoner"
                        else settings.runpod_coder_endpoint_id
                    )
                    if not ep_id:
                        raise RuntimeError("RunPod endpoint ID not configured")
                    result = await self.call_runpod(ep_id, attempt_model, messages, **kwargs)

                result["_backend_used"] = attempt_backend
                result["_model_used"]   = attempt_model
                result["_role"]         = model_role
                return result

            except Exception as e:
                last_err = e
                log.warning(
                    "backend failed, trying next",
                    failed=attempt_backend,
                    error=str(e)
                )
                continue

        raise RuntimeError(f"All backends failed for role={model_role}: {last_err}")


# Singleton
router = ComputeRouter()
