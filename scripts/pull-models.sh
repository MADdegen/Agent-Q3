#!/bin/bash
set -e

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║      Agent-Q3 Ollama — 5 Local + 4 Cloud Model Stack              ║"
echo "╚══════════════════════════════════════════════════════════════════╝"

# Start Ollama in background
ollama serve &
OLLAMA_PID=$!

# Wait for readiness
echo "[1/3] Waiting for Ollama..."
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

# ── [2/3] Ollama Cloud sign-in (if device key mounted) ──────────────────────
# Cloud models (kimi-k2:1t-cloud, gpt-oss:120b-cloud, etc.) require the
# device's SSH keypair at /root/.ollama/id_ed25519. Mount it via docker-compose
# volume (e.g. ~/.ollama:/root/.ollama). If present, signin is a no-op since
# the key already proves identity. If missing, cloud models will fail gracefully.
echo "[2/3] Checking Ollama Cloud signin..."
if [ -f /root/.ollama/id_ed25519 ]; then
  echo "      ✓ device key found — cloud models enabled"
  # ollama doesn't expose a non-interactive signin; the keypair IS the credential.
else
  echo "      ⚠ no device key — cloud models will be unavailable"
  echo "      run: docker exec -it agent-q3-ollama ollama signin"
  echo "      OR mount your host ~/.ollama into the container"
fi

# ── [3/3] Pull all local models (skip if cached) ────────────────────────────
echo "[3/3] Pulling local model stack..."

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
    ollama pull "$model" 2>&1 | tail -1 && echo "    ✓ ready" || echo "    ✗ failed (continuing)"
  fi
  echo ""
}

pull_model "${REASONER_MODEL:-hf.co/mradermacher/Kimi-VL-A3B-Instruct-i1-GGUF:Q4_K_M}" \
           "[L1] Kimi-VL-A3B Q4_K_M       — instruct / vision / agent"
pull_model "${TANDEM_MODEL:-hermes3:8b}" \
           "[L2] Hermes3 8B               — tandem reasoning"
pull_model "${CODER_MODEL:-hf.co/DavidAU/Qwen3-48B-A4B-Savant-Commander-Distill-12X-Closed-Open-Heretic-Uncensored-GGUF:Q8_0}" \
           "[L3] Qwen3-48B-A4B Q8_0       — primary multimodal"
pull_model "${FALLBACK_MODEL:-hf.co/Jackrong/Qwopus3.6-27B-v1-preview-GGUF:Q8_0}" \
           "[L4] Qwopus3.6-27B Q8_0       — fallback multimodal"
pull_model "${CODER_DEDICATED_MODEL:-hf.co/Qwen/Qwen3-Coder-30B-A3B-Instruct-GGUF:Q6_K}" \
           "[L5] Qwen3-Coder-30B-A3B Q6_K — dedicated coder"

echo "════════════════════════════════════════════════════════════════════"
echo "  Local stack ready. Cloud models routed via signed-in Ollama Cloud:"
echo "    [C1] kimi-k2:1t-cloud         — Kimi K2 monitor"
echo "    [C2] gpt-oss:120b-cloud       — frontier reasoner overflow"
echo "    [C3] qwen3-coder:480b-cloud   — frontier coder overflow"
echo "    [C4] deepseek-v3.1:671b-cloud — frontier deep-research"
echo "  Ollama API: http://0.0.0.0:11434"
echo "════════════════════════════════════════════════════════════════════"

wait $OLLAMA_PID
