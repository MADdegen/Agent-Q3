"""
Compute Router — Agent-Q3
Local GGUF stack: Kimi-VL-A3B (reasoner) + Hermes3-8B (tandem) + Qwen3-48B-Savant (coder)
                  Qwopus3.6-27B (fallback) + Qwen3-Coder-30B-A3B (coder_dedicated)
Monitor: kimi-k2:1t-cloud (Ollama Cloud — outside this router)
Priority chain: Local Ollama → OpenRouter → HuggingFace → RunPod
"""

import time
from enum import Enum
from typing import Optional
import httpx
import structlog

from .config import settings

log = structlog.get_logger(__name__)


class Backend(str, Enum):
    LOCAL      = "local"
    HF         = "huggingface"
    RUNPOD     = "runpod"
    OPENROUTER = "openrouter"


class BackendHealth:
    def __init__(self):
        self.healthy: bool = True
        self.last_check: float = 0
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


# Maps model role → local Ollama GGUF model string
#   reasoner        Kimi-VL-A3B Q4_K_M         — primary instruct / vision / agent
#   tandem          Hermes3 8B                  — reasoning partner / tandem stage-2
#   coder           Qwen3-48B-A4B-Savant        — primary multimodal / tandem stage-3
#   fallback        Qwopus3.6-27B               — fallback multimodal
#   coder_dedicated Qwen3-Coder-30B-A3B         — dedicated coder service
LOCAL_MODEL_MAP = {
    "reasoner":        lambda: settings.reasoner_model,
    "tandem":          lambda: settings.tandem_model,
    "coder":           lambda: settings.coder_model,
    "fallback":        lambda: settings.fallback_model,
    "coder_dedicated": lambda: settings.coder_dedicated_model,
}

HF_MODEL_MAP = {
    "reasoner":        lambda: settings.hf_reasoner_model,
    "tandem":          lambda: settings.hf_tandem_model,
    "coder":           lambda: settings.hf_coder_model,
    "fallback":        lambda: settings.hf_coder_model,
    "coder_dedicated": lambda: settings.hf_frontier_coder,
}

OPENROUTER_MODEL_MAP = {
    "reasoner":        lambda: settings.openrouter_reasoner_model,
    "tandem":          lambda: settings.openrouter_tandem_model,
    "coder":           lambda: settings.openrouter_coder_model,
    "fallback":        lambda: settings.openrouter_fallback_model,
    "coder_dedicated": lambda: settings.openrouter_coder_model,
}

# cloud_priority fallback chain: LOCAL → OPENROUTER → HF → RUNPOD
CLOUD_PRIORITY_CHAIN = [Backend.LOCAL, Backend.OPENROUTER, Backend.HF, Backend.RUNPOD]


class ComputeRouter:
    """
    Routes inference across Local Ollama / OpenRouter / HuggingFace Router / RunPod.
    Primary: 5-model local GGUF stack (pulled from HuggingFace via Ollama).
    Fallback chain (cloud_priority): LOCAL → OPENROUTER → HF → RUNPOD.
    Monitor (kimi-k2:1t-cloud) is handled separately in services/monitor.py.
    """

    def __init__(self):
        self._health: dict[Backend, BackendHealth] = {
            Backend.LOCAL:      BackendHealth(),
            Backend.HF:         BackendHealth(),
            Backend.RUNPOD:     BackendHealth(),
            Backend.OPENROUTER: BackendHealth(),
        }
        self._rr_counter: int = 0
        self._weights = {
            Backend.LOCAL:      settings.local_weight,
            Backend.HF:         settings.hf_weight,
            Backend.RUNPOD:     settings.runpod_weight,
            Backend.OPENROUTER: settings.openrouter_weight,
        }
        self._weighted_order: list[Backend] = self._build_weighted_order()

    def _build_weighted_order(self) -> list[Backend]:
        order = []
        for backend, weight in self._weights.items():
            order.extend([backend] * weight)
        return order

    def _next_backend(self) -> Backend:
        total = len(self._weighted_order)
        for _ in range(total):
            candidate = self._weighted_order[self._rr_counter % total]
            self._rr_counter += 1
            if self._health[candidate].healthy:
                return candidate
        log.warning("all backends unhealthy, forcing local")
        return Backend.LOCAL

    def select_backend(self, force: Backend | None = None) -> Backend:
        if force:
            return force
        if settings.compute_strategy == "cloud_priority":
            # Try in chain order: LOCAL → OPENROUTER → HF → RUNPOD
            for backend in CLOUD_PRIORITY_CHAIN:
                if self._health[backend].healthy:
                    return backend
            return Backend.LOCAL
        if settings.compute_strategy == "local_first":
            return Backend.LOCAL if self._health[Backend.LOCAL].healthy else Backend.HF
        if settings.compute_strategy == "hf_first":
            return Backend.HF if self._health[Backend.HF].healthy else Backend.LOCAL
        if settings.compute_strategy == "runpod_first":
            return Backend.RUNPOD if self._health[Backend.RUNPOD].healthy else Backend.LOCAL
        if settings.compute_strategy == "openrouter_first":
            return Backend.OPENROUTER if self._health[Backend.OPENROUTER].healthy else Backend.LOCAL
        return self._next_backend()

    # ── Backend implementations ───────────────────────────────────────────────

    async def call_local(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        **kwargs
    ) -> dict:
        payload = {"model": model, "messages": messages, "stream": stream, **kwargs}
        h = self._health[Backend.LOCAL]
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_secs) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json=payload
                )
                r.raise_for_status()
                h.mark_success()
                return r.json()
        except Exception as e:
            h.mark_error()
            log.error("local backend error", model=model, error=str(e))
            raise

    async def call_hf(
        self,
        model_id: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """HuggingFace Router — OpenAI-compatible chat completions."""
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
            async with httpx.AsyncClient(timeout=settings.request_timeout_secs) as client:
                r = await client.post(
                    f"{settings.hf_router_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                r.raise_for_status()
                h.mark_success()
                raw = r.json()
                text = raw["choices"][0]["message"]["content"]
                return {
                    "message": {"role": "assistant", "content": text},
                    "backend": Backend.HF,
                    "model": model_id,
                    "usage": raw.get("usage"),
                }
        except Exception as e:
            h.mark_error()
            log.error("HF backend error", model=model_id, error=str(e))
            raise

    async def call_runpod(
        self,
        endpoint_id: str,
        model: str,
        messages: list[dict],
        **kwargs
    ) -> dict:
        """RunPod serverless — Ollama-compatible handler expected."""
        if not settings.runpod_api_key:
            raise RuntimeError("RUNPOD_API_KEY not configured")
        h = self._health[Backend.RUNPOD]
        headers = {
            "Authorization": f"Bearer {settings.runpod_api_key}",
            "Content-Type": "application/json",
        }
        payload = {"input": {"model": model, "messages": messages, **kwargs}}
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_secs) as client:
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
                    "message": output.get("message", {"role": "assistant", "content": str(output)}),
                    "backend": Backend.RUNPOD,
                    "model": model,
                    "runpod_job_id": data.get("id"),
                }
        except Exception as e:
            h.mark_error()
            log.error("RunPod backend error", model=model, error=str(e))
            raise

    async def call_openrouter(self, model: str, messages: list[dict], **kwargs) -> dict:
        """OpenRouter cloud inference — secondary compute tier."""
        if not settings.openrouter_api_key:
            raise RuntimeError("OPENROUTER_API_KEY not configured")
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "HTTP-Referer": "https://github.com/MADdegen/Agent-Q3",
            "X-Title": "Agent-Q3",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens", 2048),
            "temperature": kwargs.get("temperature", 0.7),
        }
        h = self._health[Backend.OPENROUTER]
        try:
            async with httpx.AsyncClient(timeout=settings.request_timeout_secs) as client:
                r = await client.post(
                    f"{settings.openrouter_api_url}/chat/completions",
                    headers=headers, json=payload
                )
                r.raise_for_status()
                h.mark_success()
                raw = r.json()
                text = raw["choices"][0]["message"]["content"]
                return {
                    "message": {"role": "assistant", "content": text},
                    "backend": Backend.OPENROUTER,
                    "model": model,
                    "usage": raw.get("usage"),
                }
        except Exception as e:
            h.mark_error()
            log.error("OpenRouter backend error", model=model, error=str(e))
            raise

    # ── Main routing entry point ──────────────────────────────────────────────

    async def route(
        self,
        model_role: str,
        messages: list[dict],
        force_backend: Backend | None = None,
        **kwargs
    ) -> dict:
        """
        Select backend → resolve model for role → call with fallback chain.

        Roles → local models:
          reasoner        → Kimi-VL-A3B Q4_K_M            /v1/instruct /v1/chat
          tandem          → Hermes3 8B                     /v1/tandem stage-2
          coder           → Qwen3-48B-A4B-Savant           /v1/code /v1/tandem stage-3
          fallback        → Qwopus3.6-27B                  /v1/fallback
          coder_dedicated → Qwen3-Coder-30B-A3B            /v1/coder /v1/coder/review

        Monitor (kimi-k2:1t-cloud) is NOT routed here — see services/monitor.py.
        """
        if model_role not in LOCAL_MODEL_MAP:
            raise ValueError(f"Unknown model_role '{model_role}'. "
                             f"Valid: {list(LOCAL_MODEL_MAP.keys())}")

        backend = self.select_backend(force_backend)

        def _resolve_model(b: Backend) -> str:
            if b == Backend.HF:
                return HF_MODEL_MAP[model_role]()
            if b == Backend.OPENROUTER:
                return OPENROUTER_MODEL_MAP[model_role]()
            return LOCAL_MODEL_MAP[model_role]()  # LOCAL and RUNPOD use local name

        log.info("routing", role=model_role, backend=backend,
                 model=_resolve_model(backend))

        # Fallback chain: chosen backend first, then rest of cloud_priority order
        if settings.compute_strategy == "cloud_priority":
            if backend in CLOUD_PRIORITY_CHAIN:
                idx = CLOUD_PRIORITY_CHAIN.index(backend)
                fallback_chain = CLOUD_PRIORITY_CHAIN[idx:] + CLOUD_PRIORITY_CHAIN[:idx]
            else:
                fallback_chain = [backend] + list(CLOUD_PRIORITY_CHAIN)
        else:
            fallback_chain = [backend, Backend.LOCAL, Backend.OPENROUTER,
                              Backend.HF, Backend.RUNPOD]
            fallback_chain = list(dict.fromkeys(fallback_chain))  # dedup, preserve order

        last_err = None
        for attempt_backend in fallback_chain:
            attempt_model = _resolve_model(attempt_backend)
            try:
                if attempt_backend == Backend.LOCAL:
                    result = await self.call_local(attempt_model, messages, **kwargs)
                elif attempt_backend == Backend.HF:
                    result = await self.call_hf(attempt_model, messages, **kwargs)
                elif attempt_backend == Backend.OPENROUTER:
                    result = await self.call_openrouter(attempt_model, messages, **kwargs)
                else:
                    ep_id = (
                        settings.runpod_reasoner_endpoint_id
                        if model_role in ("reasoner", "tandem")
                        else settings.runpod_coder_endpoint_id
                    )
                    if not ep_id:
                        raise RuntimeError("RunPod endpoint not configured")
                    result = await self.call_runpod(ep_id, attempt_model, messages, **kwargs)

                result["_backend_used"] = attempt_backend
                result["_model_used"]   = attempt_model
                result["_role"]         = model_role
                return result

            except Exception as e:
                last_err = e
                log.warning("backend failed, trying next",
                            failed=attempt_backend, role=model_role, error=str(e))
                continue

        raise RuntimeError(f"All backends failed for role={model_role}: {last_err}")


# Singleton
router = ComputeRouter()
