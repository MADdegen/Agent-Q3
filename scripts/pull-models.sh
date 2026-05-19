#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║           Agent-Q3  —  Ollama Cloud Model Stack                   ║"
echo "║           ALL inference routed via Ollama Cloud                    ║"
echo "║           Account: nicholasjmcleod@gmail.com                       ║"
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
  echo "      ✓ Cloud models available via ollama.com"
else
  echo ""
  echo "  ╔══════════════════════════════════════════════════════════════╗"
  echo "  ║  ⚠  CLOUD SIGN-IN REQUIRED                                   ║"
  echo "  ║                                                                ║"
  echo "  ║  No device key found at /root/.ollama/id_ed25519              ║"
  echo "  ║                                                                ║"
  echo "  ║  Option A — Mount your host ~/.ollama (recommended):          ║"
  echo "  ║    In docker-compose.yml, under the 'ollama' service,         ║"
  echo "  ║    uncomment:                                                  ║"
  echo "  ║      - \${HOME}/.ollama:/root/.ollama                          ║"
  echo "  ║                                                                ║"
  echo "  ║  Option B — Sign in interactively:                            ║"
  echo "  ║    docker exec -it agent-q3-ollama ollama signin              ║"
  echo "  ║    (use account: nicholasjmcleod@gmail.com)                   ║"
  echo "  ╚══════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  Continuing — cloud model calls will fail until signed in."
fi
echo ""

# ── [3/3] Verify cloud models are reachable (warm-up ping) ──────────────────
echo "[3/3] Verifying Ollama Cloud model reachability..."

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

check_cloud_model "kimi-k2:1t-cloud"          "[reasoner / monitor]"
check_cloud_model "gpt-oss:120b-cloud"         "[tandem]"
check_cloud_model "qwen3-coder:480b-cloud"     "[coder / coder_dedicated]"
check_cloud_model "deepseek-v3.1:671b-cloud"   "[fallback]"

echo ""
echo "════════════════════════════════════════════════════════════════════"
echo "  No local GGUFs — all inference via Ollama Cloud"
echo ""
echo "  Role → Cloud Model:"
echo "    reasoner        kimi-k2:1t-cloud           /v1/instruct /v1/chat"
echo "    tandem          gpt-oss:120b-cloud          /v1/tandem stage-2"
echo "    coder           qwen3-coder:480b-cloud      /v1/code /v1/tandem stage-3"
echo "    fallback        deepseek-v3.1:671b-cloud    /v1/fallback"
echo "    coder_dedicated qwen3-coder:480b-cloud      /v1/coder /v1/coder/review"
echo "    monitor         kimi-k2:1t-cloud            /v1/monitor/analyze"
echo ""
echo "  Ollama API: http://0.0.0.0:11434"
echo "════════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID
