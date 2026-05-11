FROM ollama/ollama:latest AS ollama-base

# ── System deps ──────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv curl wget \
    && rm -rf /var/lib/apt/lists/*

# ── Python env ───────────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r requirements.txt

# ── Orchestrator source ───────────────────────────────────────────────────────
COPY orchestrator/ ./orchestrator/
COPY scripts/start.sh /start.sh
RUN chmod +x /start.sh

# ── Ports ─────────────────────────────────────────────────────────────────────
# 11434 → Ollama raw API
# 8000  → Orchestrator API (routed external)
EXPOSE 11434 8000

# ── Env defaults ─────────────────────────────────────────────────────────────
ENV OLLAMA_HOST=0.0.0.0 \
    OLLAMA_ORIGINS="*" \
    OLLAMA_NUM_GPU=99 \
    OLLAMA_KEEP_ALIVE=24h \
    OLLAMA_MAX_LOADED_MODELS=2 \
    PORT=8000 \
    REASONER_MODEL=gemma4:e4b-instruct-q4_K_M \
    CODER_MODEL=qwen3.5:4b-instruct-q4_K_M \
    COMPUTE_STRATEGY=round_robin \
    LOCAL_WEIGHT=60 \
    HF_WEIGHT=25 \
    RUNPOD_WEIGHT=15

ENTRYPOINT ["/start.sh"]
