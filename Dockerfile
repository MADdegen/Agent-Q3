FROM ollama/ollama:latest

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv curl wget \
    && rm -rf /var/lib/apt/lists/*

# ── Python venv (avoids PEP 668 externally-managed-environment block) ─────────
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# ── Python deps ───────────────────────────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# ── Orchestrator source ───────────────────────────────────────────────────────
COPY orchestrator/ ./orchestrator/
COPY scripts/start.sh /start.sh
RUN chmod +x /start.sh

# ── Ports ─────────────────────────────────────────────────────────────────────
# 11434 → Ollama raw API
# 8000  → Orchestrator API (external)
EXPOSE 11434 8000

# ── Env defaults ──────────────────────────────────────────────────────────────
# Railway provides $PORT at runtime — default to 8000 for local dev
ENV OLLAMA_HOST=0.0.0.0 \
    OLLAMA_ORIGINS="*" \
    OLLAMA_NUM_GPU=99 \
    OLLAMA_KEEP_ALIVE=24h \
    OLLAMA_MAX_LOADED_MODELS=2 \
    REASONER_MODEL=gemma4:e4b-instruct-q4_K_M \
    CODER_MODEL=qwen3.5:4b-instruct-q4_K_M \
    COMPUTE_STRATEGY=round_robin \
    LOCAL_WEIGHT=60 \
    HF_WEIGHT=25 \
    RUNPOD_WEIGHT=15

ENTRYPOINT ["/start.sh"]
