#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║              Agent-Q3 Ollama — 5-Model Cloud Stack                ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for readiness
echo "[1/2] Waiting for Ollama..."
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

# Pull all 5 models (skip if cached)
echo "[2/2] Pulling model stack..."

pull_model() {
  local model=$1
  local label=$2
  local short_name
  short_name=$(echo "$model" | sed 's|hf.co/||' | cut -d: -f1)
  echo "  ► ${label}"
  echo "    ${model}"
  if ollama list | grep -qF "$short_name"; then
    echo "    ✓ cached — skipping"
  else
    ollama pull "$model" && echo "    ✓ ready"
  fi
  echo ""
}

pull_model "${REASONER_MODEL:-hf.co/mradermacher/Kimi-VL-A3B-Instruct-i1-GGUF:Q4_K_M}" \
           "[1] Kimi-VL-A3B Q4_K_M       — instruct / vision / agent"
pull_model "${TANDEM_MODEL:-hermes3:8b}" \
           "[2] Hermes3 8B               — tandem reasoning"
pull_model "${CODER_MODEL:-hf.co/DavidAU/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-GGUF:Q8_0}" \
           "[3] Qwen3-48B-A4B Q8_0       — primary multimodal"
pull_model "${FALLBACK_MODEL:-hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0}" \
           "[4] Qwopus3.6-27B Q8_0       — fallback multimodal"
pull_model "${CODER_DEDICATED_MODEL:-hf.co/Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q6_K}" \
           "[5] Qwen3-Coder-30B-A3B Q6_K — dedicated coder"

echo "════════════════════════════════════════════════════════════════════"
echo "  All 5 models loaded — Ollama API: http://0.0.0.0:11434"
echo "════════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID
