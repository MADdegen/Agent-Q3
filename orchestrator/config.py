from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Ollama Cloud model stack — ALL inference via cloud (nicholasjmcleod@gmail.com) ──
    # Device: LN-8RDGA90Ultra  |  No local GGUFs, no GPU required on host
    #
    # Role → Cloud model mapping:
    #   reasoner       → kimi-k2:1t-cloud      (instruct / vision / agent / long-ctx)
    #   tandem         → gpt-oss:120b-cloud     (reasoning partner)
    #   coder          → qwen3-coder:480b-cloud (primary multimodal / code / tandem-stage3)
    #   fallback       → deepseek-v3.1:671b-cloud (fallback / deep research overflow)
    #   coder_dedicated→ qwen3-coder:480b-cloud (dedicated coder service)
    #   monitor        → kimi-k2:1t-cloud       (always-on Kimi K2 monitor)
    reasoner_model:        str = "kimi-k2:1t-cloud"
    tandem_model:          str = "gpt-oss:120b-cloud"
    coder_model:           str = "qwen3-coder:480b-cloud"
    fallback_model:        str = "deepseek-v3.1:671b-cloud"
    coder_dedicated_model: str = "qwen3-coder:480b-cloud"

    ollama_base_url: str = "http://ollama:11434"
    openwebui_url:   str = "http://localhost:3000"

    # ── Ollama Cloud sign-in ──────────────────────────────────────────────────
    # Requires: docker exec -it agent-q3-ollama ollama signin
    # OR: mount host ~/.ollama (already has id_ed25519) into the container
    ollama_cloud_enabled: bool = True
    ollama_cloud_account: str  = "nicholasjmcleod@gmail.com"
    ollama_cloud_device:  str  = "LN-8RDGA90Ultra"

    # ── Kimi K2 monitor (always-on, outside orchestration) ───────────────────
    # Primary:  Ollama Cloud  kimi-k2:1t-cloud  (same Ollama API, cloud-routed)
    # Fallback: OpenRouter    moonshotai/kimi-k2 (if cloud signin missing)
    kimi_k2_model:              str = "kimi-k2:1t-cloud"
    kimi_k2_fallback_model:     str = "moonshotai/kimi-k2"
    kimi_k2_api_url:            str = "https://openrouter.ai/api/v1"
    kimi_k2_poll_interval_secs: int = 30
    monitor_targets:            str = (
        "http://multimodal:8000,http://coder:8001,"
        "http://research:8002,http://mcp-bridge:8004,http://ollama:11434"
    )

    # ── HuggingFace — 3 tokens, auto-rotate on 429 ───────────────────────────
    hf_token:   str = ""
    hf_token_2: str = ""
    hf_token_3: str = ""
    hf_router_url:        str = "https://router.huggingface.co/v1"
    hf_reasoner_model:    str = "moonshotai/Kimi-K2-Instruct"
    hf_coder_model:       str = "Qwen/Qwen3-Coder-480B-A35B-Instruct:cerebras"
    hf_frontier_reasoner: str = "zai-org/GLM-4.5:fireworks-ai"
    hf_frontier_coder:    str = "Qwen/Qwen3-Coder-480B-A35B-Instruct:cerebras"

    # ── RunPod serverless (GPU burst if ever needed) ──────────────────────────
    runpod_api_key:              str = ""
    runpod_s3_key:               str = ""
    runpod_reasoner_endpoint_id: str = "kukl55t0053lob"
    runpod_coder_endpoint_id:    str = "kukl55t0053lob"
    runpod_api_url:              str = "https://api.runpod.ai/v2"

    # ── OpenRouter (fallback + monitor fallback) ──────────────────────────────
    openrouter_api_key:        str = ""
    openrouter_api_url:        str = "https://openrouter.ai/api/v1"
    openrouter_reasoner_model: str = "moonshotai/kimi-k2"
    openrouter_coder_model:    str = "qwen/qwen3-coder-480b-a35b-instruct"

    # ── Search + Research tools ───────────────────────────────────────────────
    perplexity_api_key:       str = ""
    perplexity_default_model: str = "sonar-pro"
    exa_api_key:              str = ""
    tavily_api_key:           str = ""
    smithery_api_key:         str = ""

    # ── Compute routing ───────────────────────────────────────────────────────
    # With all-cloud models, "local" Ollama IS the cloud — weight stays at 100
    compute_strategy: Literal[
        "round_robin", "load_based",
        "local_first", "hf_first",
        "runpod_first", "openrouter_first"
    ] = "local_first"          # local_first = Ollama Cloud first (it IS the cloud)
    local_weight:  int = 100
    hf_weight:     int = 0
    runpod_weight: int = 0

    # ── Shared infrastructure ─────────────────────────────────────────────────
    database_url: str = ""
    redis_url:    str = ""

    # ── Server ────────────────────────────────────────────────────────────────
    port:                  int = 8000
    log_level:             str = "info"
    local_max_queue:       int = 8
    hf_max_queue:          int = 8
    request_timeout_secs:  int = 300   # cloud inference can be slower than local

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

    def has_kimi_k2(self) -> bool:
        return self.ollama_cloud_enabled or bool(self.openrouter_api_key)


settings = Settings()
