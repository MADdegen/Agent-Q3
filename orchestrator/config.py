from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Ollama Cloud model stack ──────────────────────────────────────────────
    # ALL inference via Ollama Cloud (nicholasjmcleod@gmail.com / LN-8RDGA90Ultra)
    # No local GGUFs. Mount host ~/.ollama for device key (id_ed25519).
    #
    #   reasoner        kimi-vl:a3b-cloud          /v1/instruct /v1/chat
    #   tandem          hermes3:8b-cloud            /v1/tandem stage-2
    #   coder           qwen3:48b-a4b-cloud         /v1/code /v1/tandem stage-3
    #   fallback        qwopus:27b-cloud            /v1/fallback
    #   coder_dedicated qwen3-coder:30b-a3b-cloud   /v1/coder /v1/coder/review
    #   monitor         kimi-k2:1t-cloud            /v1/monitor/analyze
    reasoner_model:        str = "kimi-vl:a3b-cloud"
    tandem_model:          str = "hermes3:8b-cloud"
    coder_model:           str = "qwen3:48b-a4b-cloud"
    fallback_model:        str = "qwopus:27b-cloud"
    coder_dedicated_model: str = "qwen3-coder:30b-a3b-cloud"

    ollama_base_url: str = "http://ollama:11434"
    openwebui_url:   str = "http://localhost:3000"

    # ── Ollama Cloud auth ─────────────────────────────────────────────────────
    # Account: nicholasjmcleod@gmail.com / Device: LN-8RDGA90Ultra
    ollama_cloud_enabled: bool = True
    ollama_cloud_account: str  = "nicholasjmcleod@gmail.com"
    ollama_cloud_device:  str  = "LN-8RDGA90Ultra"

    # ── Kimi K2 always-on monitor ─────────────────────────────────────────────
    kimi_k2_model:              str = "kimi-k2:1t-cloud"
    kimi_k2_fallback_model:     str = "moonshotai/kimi-k2"
    kimi_k2_api_url:            str = "https://openrouter.ai/api/v1"
    kimi_k2_poll_interval_secs: int = 30
    monitor_targets:            str = (
        "http://multimodal:8000,http://coder:8001,"
        "http://research:8002,http://mcp-bridge:8004,http://ollama:11434"
    )

    # ── [2] OpenRouter — secondary compute ───────────────────────────────────
    openrouter_api_key:        str = ""
    openrouter_api_url:        str = "https://openrouter.ai/api/v1"
    openrouter_reasoner_model: str = "moonshotai/kimi-k2"
    openrouter_coder_model:    str = "qwen/qwen3-coder-30b-a3b-instruct"
    openrouter_tandem_model:   str = "nousresearch/hermes-3-llama-3.1-8b"
    openrouter_fallback_model: str = "deepseek/deepseek-chat-v3-5"

    # ── [3] HuggingFace Router — tertiary compute ─────────────────────────────
    hf_token:   str = ""
    hf_token_2: str = ""
    hf_token_3: str = ""
    hf_router_url:        str = "https://router.huggingface.co/v1"
    hf_reasoner_model:    str = "moonshotai/Kimi-K2-Instruct"
    hf_tandem_model:      str = "NousResearch/Hermes-3-Llama-3.1-8B"
    hf_coder_model:       str = "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    hf_frontier_reasoner: str = "moonshotai/Kimi-K2-Instruct"
    hf_frontier_coder:    str = "Qwen/Qwen3-Coder-30B-A3B-Instruct"

    # ── [4] RunPod Serverless — quaternary GPU burst ──────────────────────────
    runpod_api_key:              str = ""
    runpod_s3_key:               str = ""
    runpod_reasoner_endpoint_id: str = "kukl55t0053lob"
    runpod_coder_endpoint_id:    str = "kukl55t0053lob"
    runpod_api_url:              str = "https://api.runpod.ai/v2"
    runpod_gpu_class:            str = "AMPERE_16"

    # ── Search + Research tools ───────────────────────────────────────────────
    perplexity_api_key:       str = ""
    perplexity_default_model: str = "sonar-pro"
    exa_api_key:              str = ""
    tavily_api_key:           str = ""
    smithery_api_key:         str = ""

    # ── Compute routing ───────────────────────────────────────────────────────
    # cloud_priority = Ollama Cloud → OpenRouter → HuggingFace → RunPod
    compute_strategy: Literal[
        "cloud_priority",
        "round_robin",
        "load_based",
        "local_first",
        "hf_first",
        "runpod_first",
        "openrouter_first",
    ] = "cloud_priority"

    local_weight:      int = 60
    openrouter_weight: int = 20
    hf_weight:         int = 15
    runpod_weight:     int = 5

    # ── Shared infrastructure ─────────────────────────────────────────────────
    database_url: str = ""
    redis_url:    str = ""

    # ── Server ────────────────────────────────────────────────────────────────
    port:                  int = 8000
    log_level:             str = "info"
    local_max_queue:       int = 8
    hf_max_queue:          int = 8
    request_timeout_secs:  int = 300

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ── Helpers ───────────────────────────────────────────────────────────────
    def active_hf_token(self) -> str:
        return self.hf_token or self.hf_token_2 or self.hf_token_3 or ""

    def has_ollama_cloud(self) -> bool:
        return self.ollama_cloud_enabled

    def has_openrouter(self) -> bool:
        return bool(self.openrouter_api_key)

    def has_hf(self) -> bool:
        return bool(self.active_hf_token())

    def has_runpod(self) -> bool:
        return bool(self.runpod_api_key and self.runpod_reasoner_endpoint_id)

    def has_perplexity(self) -> bool:
        return bool(self.perplexity_api_key)

    def has_exa(self) -> bool:
        return bool(self.exa_api_key)

    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)

    def has_kimi_k2(self) -> bool:
        return self.ollama_cloud_enabled or bool(self.openrouter_api_key)


settings = Settings()
