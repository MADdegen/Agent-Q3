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

    # -- RunPod Serverless ---------------------------------------------------
    runpod_api_key: str    = ""
    runpod_endpoint_id: str = ""

    # -- OpenRouter fallback -------------------------------------------------
    openrouter_api_key: str = ""

    # -- Perplexity deep research -------------------------------------------
    perplexity_api_key: str = ""

    # -- Search APIs (optional - free_search.py works without these) --------
    exa_api_key: str      = ""
    tavily_api_key: str   = ""
    brave_api_key: str    = ""
    firecrawl_api_key: str = ""

    # -- GitHub PAT for GitHub search tool ----------------------------------
    github_pat: str = ""

    # -- Compute routing strategy -------------------------------------------
    compute_strategy: Literal[
        "round_robin", "load_based", "local_first",
        "hf_first", "runpod_first", "openrouter_first"
    ] = "local_first"
    local_weight: int   = 60
    hf_weight: int      = 25
    runpod_weight: int  = 15

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
