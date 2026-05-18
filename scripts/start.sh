#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║           Agent-Q3 — MAD Gambit Orchestrator             ║"
echo "║   Reasoner: Gemma4-E4B  |  Coder: Qwen3.5-4B            ║"
echo "╚══════════════════════════════════════════════════════════╝"

# ── 1. Start Ollama server in background ─────────────────────────────────────
echo "[1/4] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# ── 2. Wait until Ollama is ready ────────────────────────────────────────────
echo "[2/4] Waiting for Ollama readiness..."
MAX_WAIT=60
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
echo "[3/4] Pulling models (Q4_K_M GGUF)..."

pull_model() {
  local model=$1
  local label=$2
  echo "  ► Pulling ${label} (${model})..."
  if ollama list | grep -q "$(echo $model | cut -d: -f1)"; then
    echo "    ✓ ${label} already cached, skipping pull"
  else
    ollama pull "$model"
    echo "    ✓ ${label} ready"
  fi
}

pull_model "${REASONER_MODEL:-gemma4:e4b-instruct-q4_K_M}" "Gemma4-E4B (Reasoner)"
pull_model "${CODER_MODEL:-qwen3.5:4b-instruct-q4_K_M}"    "Qwen3.5-4B (Coder)"

echo "      Both models loaded ✓"

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
echo "══════════════════════════════════════════════════════════════"
echo "  Orchestrator : http://0.0.0.0:${PORT:-8000}"
echo "  Ollama API   : http://0.0.0.0:11434"
echo "  Reasoner     : ${REASONER_MODEL}"
echo "  Coder        : ${CODER_MODEL}"
echo "  Strategy     : ${COMPUTE_STRATEGY:-round_robin}"
echo "══════════════════════════════════════════════════════════════"

# Keep both processes alive — exit if either dies
wait $OLLAMA_PID $ORCH_PID
