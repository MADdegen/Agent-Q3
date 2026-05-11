from pydantic_settings import BaseSettings
from typing import Literal
import os


class Settings(BaseSettings):
    # ── Model identifiers ────────────────────────────────────────────────────
    reasoner_model: str = "gemma4:e4b-instruct-q4_K_M"   # Gemma4-E4B
    coder_model: str    = "qwen3.5:4b-instruct-q4_K_M"   # Qwen3.5-4B

    # ── Local Ollama ──────────────────────────────────────────────────────────
    ollama_base_url: str = "http://localhost:11434"

    # ── HuggingFace Inference ─────────────────────────────────────────────────
    hf_token: str = ""
    # HF model IDs for fallback (mirror of local models via HF Inference API)
    hf_reasoner_model: str = "google/gemma-4-e4b-it"
    hf_coder_model: str    = "Qwen/Qwen3.5-4B-Instruct"
    hf_api_url: str        = "https://api-inference.huggingface.co/models"

    # ── RunPod Serverless ─────────────────────────────────────────────────────
    runpod_api_key: str         = ""
    runpod_reasoner_endpoint_id: str = ""  # RunPod serverless endpoint for Gemma4
    runpod_coder_endpoint_id: str    = ""  # RunPod serverless endpoint for Qwen3.5
    runpod_api_url: str              = "https://api.runpod.ai/v2"

    # ── Compute routing ───────────────────────────────────────────────────────
    compute_strategy: Literal["round_robin", "load_based", "local_first", "hf_first", "runpod_first"] = "round_robin"
    local_weight: int   = 60   # % of requests → local Ollama
    hf_weight: int      = 25   # % of requests → HuggingFace
    runpod_weight: int  = 15   # % of requests → RunPod

    # ── Server ────────────────────────────────────────────────────────────────
    port: int  = 8000
    log_level: str = "info"

    # ── Health thresholds ─────────────────────────────────────────────────────
    local_max_queue: int     = 4    # if local queue > this → spill to HF
    hf_max_queue: int        = 8    # if HF queue > this → spill to RunPod
    request_timeout_secs: int = 120

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
