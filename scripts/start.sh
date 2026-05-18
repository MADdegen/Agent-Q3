#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║                Agent-Q3 — MAD Gambit Orchestrator                ║"
echo "║  Instruct : Kimi-VL-A3B  +  Hermes3 [tandem]                    ║"
echo "║  Multimodal: Qwen3-48B-A4B  |  Fallback: Qwopus3.6-27B          ║"
echo "║  GUI      : Open WebUI → port 3000                               ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

# ── 1. Start Ollama ───────────────────────────────────────────────────────────
echo "[1/4] Starting Ollama server..."
ollama serve &
OLLAMA_PID=$!

# ── 2. Wait for Ollama ───────────────────────────────────────────────────────
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

# ── 3. Pull all models (skip if cached) ──────────────────────────────────────
echo "[3/4] Pulling model stack..."

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
    ollama pull "$model"
    echo "    ✓ ready"
  fi
  echo ""
}

# [1] Primary instruct — Kimi-VL-A3B iMatrix (vision + instruct, 3B)
pull_model \
  "${REASONER_MODEL:-hf.co/mradermacher/Kimi-VL-A3B-Instruct-i1-GGUF:Q4_K_M}" \
  "Kimi-VL-A3B Q4_K_M  [PRIMARY INSTRUCT — vision+long-ctx]"

# [2] Tandem instruct — Hermes3 8B (reasoning support for Kimi)
pull_model \
  "${TANDEM_MODEL:-hermes3:8b}" \
  "Hermes3 8B           [TANDEM INSTRUCT — reasoning partner]"

# [3] Primary multimodal — Qwen3-48B A4B active MoE
pull_model \
  "${CODER_MODEL:-hf.co/DavidAU/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-GGUF:Q8_0}" \
  "Qwen3-48B-A4B Q8_0 (DavidAU)  [PRIMARY MULTIMODAL — 4B active MoE]"

# [4] Fallback multimodal — Qwopus3.6-27B
pull_model \
  "${FALLBACK_MODEL:-hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0}" \
  "Qwopus3.6-27B Q8_0  [FALLBACK MULTIMODAL]"

echo "      All 4 models loaded ✓"

# ── 4. Start Orchestrator ─────────────────────────────────────────────────────
echo "[4/4] Launching Orchestrator on port ${PORT:-8000}..."
cd /app
python3 -m uvicorn orchestrator.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --log-level info \
  --access-log &

ORCH_PID=$!
echo ""
echo "══════════════════════════════════════════════════════════════════════"
echo "  Open WebUI (GUI) : http://0.0.0.0:3000"
echo "  Orchestrator API : http://0.0.0.0:${PORT:-8000}"
echo "  Ollama raw API   : http://0.0.0.0:11434"
echo ""
echo "  [1] Instruct      : ${REASONER_MODEL}"
echo "  [2] Tandem        : ${TANDEM_MODEL}"
echo "  [3] Multimodal    : ${CODER_MODEL}"
echo "  [4] Fallback      : ${FALLBACK_MODEL}"
echo "  Strategy          : ${COMPUTE_STRATEGY:-round_robin}"
echo "══════════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID $ORCH_PID
