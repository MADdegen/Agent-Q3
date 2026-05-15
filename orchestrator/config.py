import os
from typing import Literal, Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # -- Local Ollama models -------------------------------------------------
    reasoner_model: str = "hf.co/unsloth/Qwen2.5-VL-32B-Instruct-GGUF:Q4_K_M"
    support_model: str  = "hf.co/TeichAI/Qwen3-8B-Kimi-K2-Thinking-Distill-GGUF:Q4_K_M"
    coder_model: str    = "hf.co/unsloth/QwQ-32B-GGUF:Q4_K_M"
    ollama_base_url: str = "http://localhost:11434"

    # -- OpenWebUI gateway ---------------------------------------------------
    openwebui_url: str = "https://open-webui-gateway-staging.up.railway.app"

    # -- HuggingFace - 3 tokens, auto-rotate on 429 -------------------------
    hf_token: str   = ""
    hf_token_2: str = ""
    hf_token_3: str = ""
    hf_reasoner_model: str = "Qwen/Qwen2.5-VL-32B-Instruct"
    hf_support_model: str  = "Qwen/Qwen3-8B"
    hf_coder_model: str    = "Qwen/QwQ-32B"
    hf_api_url: str        = "https://api-inference.huggingface.co/models"
    hf_weekly_limit: int   = 1000

    # -- RunPod Serverless (legacy single-endpoint) --------------------------
    runpod_api_key: str             = ""
    runpod_endpoint_id: str         = ""
    runpod_api_url: str             = "https://api.runpod.ai/v2"
    runpod_reasoner_endpoint_id: str = ""
    runpod_coder_endpoint_id: str   = ""

    # -- RunPod Community Cloud (Tier 2) -------------------------------------
    runpod_community_1: str = os.getenv("RUNPOD_COMMUNITY_1", "http://localhost:11434")
    runpod_community_2: str = os.getenv("RUNPOD_COMMUNITY_2", "http://localhost:11434")

    # -- RunPod Serverless endpoints (Tier 3) --------------------------------
    runpod_serverless_1: str = os.getenv("RUNPOD_SERVERLESS_1", "")
    runpod_serverless_2: str = os.getenv("RUNPOD_SERVERLESS_2", "")

    # -- OpenRouter (Tier 4 guaranteed fallback) -----------------------------
    openrouter_api_key: str  = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # -- Perplexity deep research -------------------------------------------
    perplexity_api_key: str = ""

    # -- Search APIs (optional - free_search.py works without these) --------
    exa_api_key: str      = ""
    tavily_api_key: str   = ""
    brave_api_key: str    = ""
    firecrawl_api_key: str = ""

    # -- GitHub PAT for GitHub search tool ----------------------------------
    github_pat: str = ""

    # -- Request timeouts ----------------------------------------------------
    request_timeout_secs: int = 120

    # -- Compute routing strategy -------------------------------------------
    compute_strategy: Literal[
        "round_robin", "load_based", "local_first",
        "hf_first", "runpod_first", "openrouter_first"
    ] = "local_first"
    local_weight: int   = 60
    hf_weight: int      = 25
    runpod_weight: int  = 15

    # -- Deployment environment ----------------------------------------------
    environment: str = "production"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
