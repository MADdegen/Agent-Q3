#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║              Agent-Q3 — MAD Gambit Orchestrator              ║"
echo "║  Instruct : Kimi K2.6  |  Multimodal : Qwen3-48B-A4B        ║"
echo "║  Fallback : Qwopus3.6-27B  |  GUI: Open WebUI :3000         ║"
echo "╚══════════════════════════════════════════════════════════════╝"

# ── 1. Start Ollama server ────────────────────────────────────────────────────
echo "[1/4] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# ── 2. Wait until Ollama is ready ────────────────────────────────────────────
echo "[2/4] Waiting for Ollama readiness..."
MAX_WAIT=120
WAITED=0
until curl -sf http://localhost:11434/ > /dev/null 2>&1; do
  sleep 2
  WAITED=$((WAITED + 2))
  if [ $WAITED -ge $MAX_WAIT ]; then
    echo "ERROR: Ollama did not start within ${MAX_WAIT}s"
    exit 1
  fi
done
echo "      Ollama ready after ${WAITED}s"

# ── 3. Pull models (skip if already cached) ───────────────────────────────────
echo "[3/4] Pulling models..."

pull_model() {
  local model=$1
  local label=$2
  local short_name
  short_name=$(echo "$model" | sed 's|hf.co/||' | cut -d: -f1)
  echo "  ► ${label} (${model})"
  if ollama list | grep -qF "$short_name"; then
    echo "    ✓ already cached, skipping"
  else
    ollama pull "$model"
    echo "    ✓ ready"
  fi
}

# Primary instruct — Kimi K2.6 (2.6B active MoE, fast + smart)
pull_model "${REASONER_MODEL:-hf.co/unsloth/Kimi-K2.6-GGUF:Q4_K_M}" \
           "Kimi K2.6 Q4_K_M [PRIMARY INSTRUCT]"

# Main multimodal — Qwen3-48B A4B active MoE
pull_model "${CODER_MODEL:-hf.co/mradermacher/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-i1-GGUF:Q6_K}" \
           "Qwen3-48B-A4B Q6_K [MAIN MULTIMODAL]"

# Fallback
pull_model "${FALLBACK_MODEL:-hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0}" \
           "Qwopus3.6-27B Q8_0 [FALLBACK]"

echo "      All models loaded ✓"

# ── 4. Start Orchestrator ─────────────────────────────────────────────────────
echo "[4/4] Launching Agent-Q3 Orchestrator on port ${PORT:-8000}..."
cd /app
python3 -m uvicorn orchestrator.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --log-level info \
  --access-log &

ORCH_PID=$!
echo ""
echo "══════════════════════════════════════════════════════════════════"
echo "  Orchestrator API : http://0.0.0.0:${PORT:-8000}"
echo "  Ollama raw API   : http://0.0.0.0:11434"
echo "  Open WebUI       : http://0.0.0.0:3000  (separate container)"
echo "  Primary instruct : ${REASONER_MODEL}"
echo "  Main multimodal  : ${CODER_MODEL}"
echo "  Fallback         : ${FALLBACK_MODEL}"
echo "  Strategy         : ${COMPUTE_STRATEGY:-round_robin}"
echo "══════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID $ORCH_PID
