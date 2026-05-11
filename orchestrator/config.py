from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Local Ollama models ───────────────────────────────────────────────────
    reasoner_model: str = "gemma4:e4b-instruct-q4_K_M"
    coder_model: str    = "qwen3.5:4b-instruct-q4_K_M"
    ollama_base_url: str = "http://localhost:11434"

    # ── OpenWebUI gateway ─────────────────────────────────────────────────────
    openwebui_url: str = "https://open-webui-gateway-staging.up.railway.app"

    # ── HuggingFace — 3 tokens, auto-rotate on 429 ────────────────────────────
    # KEY: HF provides an OpenAI-compatible router at router.huggingface.co/v1
    # This allows calling ANY HF model via the same OpenAI chat completions API.
    # Used by both agents for frontier model access (GLM-4.5, DeepSeek-V3, Qwen-Coder etc.)
    hf_token: str          = ""
    hf_token_2: str        = ""
    hf_token_3: str        = ""
    hf_router_url: str     = "https://router.huggingface.co/v1"   # ← from providers.ts
    hf_api_url: str        = "https://api-inference.huggingface.co/models"
    hf_chat_api_url: str   = "https://api-inference.huggingface.co/v1/chat/completions"
    # Default models via HF Router
    hf_reasoner_model: str = "google/gemma-4-e4b-it"
    hf_coder_model: str    = "Qwen/Qwen3.5-4B-Instruct"
    # Optional upgraded HF router models (frontier, no cost if on HF PRO)
    hf_frontier_reasoner: str = "zai-org/GLM-4.5:fireworks-ai"           # 130B, reasoning
    hf_frontier_coder: str    = "Qwen/Qwen3-Coder-480B-A35B-Instruct:cerebras"  # best OSS coder

    # ── RunPod serverless ─────────────────────────────────────────────────────
    runpod_api_key: str              = ""
    runpod_s3_key: str               = ""
    runpod_reasoner_endpoint_id: str = "kukl55t0053lob"
    runpod_coder_endpoint_id: str    = "kukl55t0053lob"
    runpod_api_url: str              = "https://api.runpod.ai/v2"

    # ── OpenRouter (frontier fallback, free tier) ─────────────────────────────
    openrouter_api_key: str        = ""
    openrouter_api_url: str        = "https://openrouter.ai/api/v1"
    openrouter_reasoner_model: str = "google/gemma-2-27b-it:free"
    openrouter_coder_model: str    = "qwen/qwen-2.5-coder-7b-instruct:free"

    # ── Search + Research tools (both agents) ─────────────────────────────────
    # Perplexity Sonar — deep research for Reasoner, doc lookup for Coder
    perplexity_api_key: str = ""
    perplexity_default_model: str = "sonar-pro"

    # Exa — semantic neural search
    exa_api_key: str = ""

    # Tavily — fast news + general search
    tavily_api_key: str = ""

    # Smithery + Glama — MCP server discovery
    smithery_api_key: str = ""

    # ── Compute routing ───────────────────────────────────────────────────────
    compute_strategy: Literal[
        "round_robin", "load_based",
        "local_first", "hf_first",
        "runpod_first", "openrouter_first"
    ] = "round_robin"
    local_weight:  int = 60
    hf_weight:     int = 25
    runpod_weight: int = 15

    # ── Shared infrastructure ─────────────────────────────────────────────────
    database_url: str = ""
    redis_url: str    = ""

    # ── Server ────────────────────────────────────────────────────────────────
    port: int              = 8000
    log_level: str         = "info"
    local_max_queue: int   = 4
    hf_max_queue: int      = 8
    request_timeout_secs: int = 180

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ── Helpers ───────────────────────────────────────────────────────────────
    def active_hf_token(self) -> str:
        """First available HF token — rotates on exhaustion."""
        return self.hf_token or self.hf_token_2 or self.hf_token_3 or ""

    def has_runpod(self) -> bool:
        return bool(self.runpod_api_key and self.runpod_reasoner_endpoint_id)

    def has_hf(self) -> bool:
        return bool(self.active_hf_token())

    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key)

    def has_perplexity(self) -> bool:
        return bool(self.perplexity_api_key)

    def has_exa(self) -> bool:
        return bool(self.exa_api_key)

    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)


settings = Settings()
