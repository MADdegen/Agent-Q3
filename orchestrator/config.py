from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Local Ollama model stack (5 GGUFs pulled from HuggingFace) ───────────
    #   reasoner        Kimi-VL-A3B Q4_K_M      /v1/instruct /v1/chat (auto)
    #   tandem          Hermes3 8B               /v1/tandem stage-2, /v1/coder/review stage-2
    #   coder           Qwen3-48B-A4B-Savant     /v1/code, /v1/tandem stage-3
    #   fallback        Qwopus3.6-27B            /v1/fallback
    #   coder_dedicated Qwen3-Coder-30B-A3B      /v1/coder, /v1/coder/review stage-1
    #   monitor         kimi-k2:1t-cloud         /v1/monitor/analyze (Ollama Cloud only)
    reasoner_model:        str = "hf.co/mradermacher/Kimi-VL-A3B-Instruct-i1-GGUF:Q4_K_M"
    tandem_model:          str = "hermes3:8b"
    coder_model:           str = "hf.co/DavidAU/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-GGUF:Q8_0"
    fallback_model:        str = "hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0"
    coder_dedicated_model: str = "hf.co/Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q6_K"

    ollama_base_url: str = "http://ollama:11434"
    openwebui_url:   str = "http://localhost:3000"

    # ── Ollama Cloud auth (monitor only — kimi-k2:1t-cloud) ──────────────────
    # Mount host ~/.ollama as volume for device key (id_ed25519)
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
    openrouter_coder_model:    str = "qwen/qwen3-coder-480b-a35b-instruct"
    openrouter_tandem_model:   str = "openai/gpt-4o"
    openrouter_fallback_model: str = "deepseek/deepseek-chat-v3-5"

    # ── [3] HuggingFace Router — tertiary compute ─────────────────────────────
    hf_token:   str = ""
    hf_token_2: str = ""
    hf_token_3: str = ""
    hf_router_url:        str = "https://router.huggingface.co/v1"
    hf_reasoner_model:    str = "moonshotai/Kimi-K2-Instruct"
    hf_coder_model:       str = "Qwen/Qwen3-Coder-480B-A35B-Instruct:cerebras"
    hf_tandem_model:      str = "zai-org/GLM-4.5:fireworks-ai"
    hf_frontier_reasoner: str = "zai-org/GLM-4.5:fireworks-ai"
    hf_frontier_coder:    str = "Qwen/Qwen3-Coder-480B-A35B-Instruct:cerebras"

    # ── [4] RunPod Serverless — quaternary GPU burst ──────────────────────────
    runpod_api_key:              str = ""
    runpod_s3_key:               str = ""
    runpod_reasoner_endpoint_id: str = "kukl55t0053lob"
    runpod_coder_endpoint_id:    str = "kukl55t0053lob"
    runpod_api_url:              str = "https://api.runpod.ai/v2"
    runpod_gpu_class:            str = "AMPERE_16"   # RTX A4000 16GB

    # ── Search + Research tools ───────────────────────────────────────────────
    perplexity_api_key:       str = ""
    perplexity_default_model: str = "sonar-pro"
    exa_api_key:              str = ""
    tavily_api_key:           str = ""
    smithery_api_key:         str = ""

    # ── Compute routing ───────────────────────────────────────────────────────
    # cloud_priority = Local Ollama → OpenRouter → HuggingFace → RunPod
    compute_strategy: Literal[
        "cloud_priority",       # Local Ollama → OpenRouter → HF → RunPod
        "round_robin",
        "load_based",
        "local_first",          # Ollama only, fall back to HF
        "hf_first",
        "runpod_first",
        "openrouter_first",
    ] = "cloud_priority"

    # Weights used in round_robin mode only (cloud_priority ignores these)
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
