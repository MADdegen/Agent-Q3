#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║           Agent-Q3  —  Ollama Cloud Model Stack                   ║"
echo "║           ALL inference via Ollama Cloud — no local GGUFs         ║"
echo "║           Account: nicholasjmcleod@gmail.com / LN-8RDGA90Ultra    ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for readiness
echo "[1/3] Waiting for Ollama daemon..."
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
echo "      ✓ Ollama ready after ${WAITED}s"
echo ""

# ── [2/3] Verify Ollama Cloud sign-in ───────────────────────────────────────
echo "[2/3] Verifying Ollama Cloud authentication..."
if [ -f /root/.ollama/id_ed25519 ]; then
  echo "      ✓ Device key found: LN-8RDGA90Ultra"
  echo "      ✓ All cloud models accessible via ollama.com"
else
  echo ""
  echo "  ╔══════════════════════════════════════════════════════════════╗"
  echo "  ║  ⚠  CLOUD SIGN-IN REQUIRED                                   ║"
  echo "  ║                                                                ║"
  echo "  ║  No device key at /root/.ollama/id_ed25519                    ║"
  echo "  ║                                                                ║"
  echo "  ║  Option A — Mount your host ~/.ollama (recommended):          ║"
  echo "  ║    volumes:                                                    ║"
  echo "  ║      - ~/.ollama:/root/.ollama                                 ║"
  echo "  ║                                                                ║"
  echo "  ║  Option B — Sign in interactively:                            ║"
  echo "  ║    docker exec -it agent-q3-ollama ollama signin              ║"
  echo "  ║    Account: nicholasjmcleod@gmail.com                         ║"
  echo "  ╚══════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  Continuing — all cloud model calls will fail until signed in."
fi
echo ""

# ── [3/3] Verify all 6 cloud models are reachable ───────────────────────────
echo "[3/3] Verifying Ollama Cloud model reachability..."
echo ""

check_cloud_model() {
  local model=$1
  local role=$2
  echo -n "      ${role}: ${model} ... "
  if ollama show "${model}" > /dev/null 2>&1; then
    echo "✓ accessible"
  else
    echo "⚠ not yet accessible (sign-in may be needed)"
  fi
}

check_cloud_model "kimi-vl:a3b-cloud"          "[reasoner]"
check_cloud_model "hermes3:8b-cloud"            "[tandem]"
check_cloud_model "qwen3:48b-a4b-cloud"         "[coder]"
check_cloud_model "qwopus:27b-cloud"            "[fallback]"
check_cloud_model "qwen3-coder:30b-a3b-cloud"   "[coder_dedicated]"
check_cloud_model "kimi-k2:1t-cloud"            "[monitor]"

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  No local GGUFs — all inference via Ollama Cloud"
echo ""
echo "  Role → Cloud Model:"
echo "    reasoner        kimi-vl:a3b-cloud          /v1/instruct /v1/chat"
echo "    tandem          hermes3:8b-cloud            /v1/tandem stage-2"
echo "    coder           qwen3:48b-a4b-cloud         /v1/code /v1/tandem stage-3"
echo "    fallback        qwopus:27b-cloud            /v1/fallback"
echo "    coder_dedicated qwen3-coder:30b-a3b-cloud   /v1/coder /v1/coder/review"
echo "    monitor         kimi-k2:1t-cloud            /v1/monitor/analyze"
echo ""
echo "  Ollama API: http://0.0.0.0:11434"
echo "════════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID
