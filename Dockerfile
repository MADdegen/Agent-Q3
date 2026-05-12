FROM python:3.12-slim

# ── System deps ───────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    curl wget \
    && rm -rf /var/lib/apt/lists/*

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
# 8000  → Orchestrator API (external)
EXPOSE 8000

# ── Env defaults ──────────────────────────────────────────────────────────────
# Railway provides $PORT at runtime — default to 8000 for local dev
ENV REASONER_MODEL=unsloth/qwen2.5-vl-32b-instruct-gguf:q4_k_m \
    CODER_MODEL=unsloth/qwq-32b-gguf:q4_k_m \
    SUPPORT_MODEL=teichai/qwen3-8b-kimi-k2-thinking-distill-gguf:q4_k_m \
    COMPUTE_STRATEGY=round_robin \
    LOCAL_WEIGHT=60 \
    HF_WEIGHT=25 \
    RUNPOD_WEIGHT=15

ENTRYPOINT ["/start.sh"]
