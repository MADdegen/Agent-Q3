#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║           Agent-Q3  —  Ollama Model Stack                         ║"
echo "║           5 local GGUFs + kimi-k2:1t-cloud (monitor)              ║"
echo "║           Cloud auth: nicholasjmcleod@gmail.com / LN-8RDGA90Ultra ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for readiness
echo "[1/4] Waiting for Ollama daemon..."
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
echo "      ✓ Ollama ready after ${WAITED}s"
echo ""

# ── [2/4] Verify Ollama Cloud sign-in (for kimi-k2:1t-cloud monitor) ────────
echo "[2/4] Checking Ollama Cloud authentication (monitor model)..."
if [ -f /root/.ollama/id_ed25519 ]; then
  echo "      ✓ Device key found: LN-8RDGA90Ultra"
  echo "      ✓ kimi-k2:1t-cloud accessible via ollama.com"
else
  echo ""
  echo "  ╔══════════════════════════════════════════════════════════════╗"
  echo "  ║  ⚠  CLOUD SIGN-IN REQUIRED (for monitor only)                ║"
  echo "  ║  Mount host ~/.ollama or run:                                 ║"
  echo "  ║    docker exec -it agent-q3-ollama ollama signin             ║"
  echo "  ║  Account: nicholasjmcleod@gmail.com                          ║"
  echo "  ╚══════════════════════════════════════════════════════════════╝"
  echo "  Continuing — monitor will use OpenRouter fallback until signed in."
fi
echo ""

# ── [3/4] Pull 5 local GGUF models ──────────────────────────────────────────
echo "[3/4] Pulling local GGUF models..."
echo ""

pull_model() {
  local tag=$1
  local role=$2
  echo "  ── ${role}"
  echo "     ${tag}"
  if ollama pull "${tag}"; then
    echo "     ✓ pulled"
  else
    echo "     ✗ FAILED — check tag / HuggingFace availability"
  fi
  echo ""
}

# reasoner — Kimi-VL-A3B Q4_K_M — /v1/instruct /v1/chat
pull_model \
  "hf.co/mradermacher/Kimi-VL-A3B-Instruct-i1-GGUF:Q4_K_M" \
  "reasoner [Kimi-VL-A3B Q4_K_M]"

# tandem — Hermes3 8B — /v1/tandem stage-2, /v1/coder/review stage-2
pull_model \
  "hermes3:8b" \
  "tandem [Hermes3 8B]"

# coder — Qwen3-48B-A4B-Savant — /v1/code, /v1/tandem stage-3
pull_model \
  "hf.co/DavidAU/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-GGUF:Q8_0" \
  "coder [Qwen3-48B-A4B-Savant Q8_0]"

# fallback — Qwopus3.6-27B — /v1/fallback
pull_model \
  "hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0" \
  "fallback [Qwopus3.6-27B Q8_0]"

# coder_dedicated — Qwen3-Coder-30B-A3B — /v1/coder, /v1/coder/review stage-1
pull_model \
  "hf.co/Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q6_K" \
  "coder_dedicated [Qwen3-Coder-30B-A3B Q6_K]"

# ── [4/4] Summary ────────────────────────────────────────────────────────────
echo "[4/4] Model stack status:"
echo ""
echo "  ollama list:"
ollama list 2>/dev/null || echo "  (ollama list unavailable)"
echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  Role → Model:"
echo "    reasoner        Kimi-VL-A3B Q4_K_M      /v1/instruct /v1/chat"
echo "    tandem          Hermes3 8B               /v1/tandem stage-2"
echo "    coder           Qwen3-48B-A4B-Savant     /v1/code /v1/tandem stage-3"
echo "    fallback        Qwopus3.6-27B            /v1/fallback"
echo "    coder_dedicated Qwen3-Coder-30B-A3B      /v1/coder /v1/coder/review"
echo "    monitor         kimi-k2:1t-cloud         /v1/monitor/analyze (cloud)"
echo ""
echo "  Ollama API: http://0.0.0.0:11434"
echo "════════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID
