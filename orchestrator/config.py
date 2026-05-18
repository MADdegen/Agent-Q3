from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Local Ollama — 4-model stack ─────────────────────────────────────────
    # [1] Primary instruct — Kimi-VL-A3B iMatrix (vision, agent, long-ctx)
    reasoner_model: str = "hf.co/mradermacher/Kimi-VL-A3B-Instruct-i1-GGUF:Q4_K_M"
    # [2] Tandem instruct  — Hermes3 8B (reasoning partner alongside Kimi)
    tandem_model: str   = "hermes3:8b"
    # [3] Primary multimodal — Qwen3-48B A4B active MoE (DavidAU Q8_0, original publisher)
    coder_model: str    = "hf.co/DavidAU/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-GGUF:Q8_0"
    # [4] Fallback multimodal — Qwopus3.6-27B
    fallback_model: str = "hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0"
    # [5] Dedicated coder — Qwen3-Coder-30B-A3B (3B active MoE, ~96%+ HumanEval)
    coder_dedicated_model: str = "hf.co/Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q6_K"

    ollama_base_url: str = "http://localhost:11434"

    # ── Open WebUI ────────────────────────────────────────────────────────────
    openwebui_url: str = "http://localhost:3000"

    # ── HuggingFace — 3 tokens, auto-rotate on 429 ────────────────────────────
    hf_token: str          = ""
    hf_token_2: str        = ""
    hf_token_3: str        = ""
    hf_router_url: str     = "https://router.huggingface.co/v1"
    hf_api_url: str        = "https://api-inference.huggingface.co/models"
    hf_chat_api_url: str   = "https://api-inference.huggingface.co/v1/chat/completions"
    hf_reasoner_model: str = "moonshotai/Kimi-VL-A3B-Instruct"
    hf_coder_model: str    = "Qwen/Qwen3.5-4B-Instruct"
    hf_frontier_reasoner: str = "zai-org/GLM-4.5:fireworks-ai"
    hf_frontier_coder: str    = "Qwen/Qwen3-Coder-480B-A35B-Instruct:cerebras"

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

    # ── Kimi K2 cloud monitor (always-on, outside local orchestration) ─────────
    kimi_k2_model: str             = "moonshotai/kimi-k2"
    kimi_k2_api_url: str           = "https://openrouter.ai/api/v1"
    kimi_k2_poll_interval_secs: int = 30
    monitor_targets: str           = "http://multimodal:8000,http://coder:8001,http://research:8002,http://ollama:11434"

    def has_kimi_k2(self) -> bool:
        return bool(self.openrouter_api_key)

    # ── Search + Research tools ───────────────────────────────────────────────
    perplexity_api_key: str        = ""
    perplexity_default_model: str  = "sonar-pro"
    exa_api_key: str               = ""
    tavily_api_key: str            = ""
    smithery_api_key: str          = ""

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
    port: int                  = 8000
    log_level: str             = "info"
    local_max_queue: int       = 4
    hf_max_queue: int          = 8
    request_timeout_secs: int  = 180

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ── Helpers ───────────────────────────────────────────────────────────────
    def active_hf_token(self) -> str:
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
