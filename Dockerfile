# ─────────────────────────────────────────────────────────────────────────────
# Agent-Q3 Python app image — used by the multimodal, coder, and research services.
# Ollama runs in its own container (ollama/ollama image) — see docker-compose.yml.
# ─────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim

# System deps
RUN apt-get update && apt-get install -y \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Source
COPY orchestrator/ ./orchestrator/
COPY config/       ./config/

EXPOSE 8000 8001 8002

# Default command runs the multimodal orchestrator.
# docker-compose overrides this per-service for coder/research.
CMD ["python", "-m", "uvicorn", "orchestrator.main:app", \
     "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
