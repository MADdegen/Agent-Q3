# Agent-Q3 — MAD Gambit Dual-Model Orchestrator

**Reasoner:** Gemma4-E4B Q4_K_M · **Coder:** Qwen3.5-4B Q4_K_M  
**Compute:** Local Ollama → HuggingFace → RunPod (weighted round-robin)

---

## Architecture

```
POST /v1/chat     → auto-classify → Reasoner or Coder
POST /v1/reason   → force Gemma4-E4B  (instruct / deep research / planning)
POST /v1/code     → force Qwen3.5-4B  (code / fetch / file ops / debug)
POST /v1/tandem   → Gemma4 reasons → Qwen3.5 implements (chained)
GET  /health      → backend health + loaded models
GET  /metrics     → Prometheus
```

**Both models run in one container** — `OLLAMA_MAX_LOADED_MODELS=2` keeps them hot simultaneously.

```
┌─────────────────────────────────────────────┐
│            Agent-Q3 Container               │
│                                             │
│  Ollama :11434                              │
│  ├── gemma4:e4b-instruct-q4_K_M  (Reasoner)│
│  └── qwen3.5:4b-instruct-q4_K_M  (Coder)   │
│                                             │
│  Orchestrator FastAPI :8000                 │
│  └── ComputeRouter                          │
│       ├── Local   (60% weight)              │
│       ├── HuggingFace (25%)                 │
│       └── RunPod  (15%)                     │
└─────────────────────────────────────────────┘
```

---

## Quick Start

```bash
cp .env.example .env
# Fill in HF_TOKEN, RUNPOD_API_KEY, RUNPOD_*_ENDPOINT_ID

docker compose up --build
```

---

## API Usage

```bash
# Auto-classify (recommended)
curl -X POST http://localhost:8000/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Write a Solidity ERC-20 contract"}]}'

# Force reasoner
curl -X POST http://localhost:8000/v1/reason \
  -d '{"messages": [{"role": "user", "content": "Research Polymarket vs MAD Gambit market design"}]}'

# Force coder
curl -X POST http://localhost:8000/v1/code \
  -d '{"messages": [{"role": "user", "content": "Fix this Hono middleware bug: ..."}]}'

# Tandem (think → implement)
curl -X POST http://localhost:8000/v1/tandem \
  -d '{"messages": [{"role": "user", "content": "Build a market resolution oracle in Solidity using Chainlink"}]}'
```

---

## Compute Strategy

| Strategy | Behaviour |
|---|---|
| `round_robin` | 60% local / 25% HF / 15% RunPod (default) |
| `local_first` | Always local, fall back to HF |
| `hf_first` | Always HF, fall back to local |
| `runpod_first` | Always RunPod, fall back to local |
| `load_based` | Routes based on queue depth |

Set `COMPUTE_STRATEGY` env var to switch at runtime.

---

## Railway Deployment

Railway project: `exciting-freedom`  
Service: `ollama-gemma4-qwen35-pair`  
Domain: `ollama-gemma4-qwen35-pair-staging.up.railway.app`

The Railway service is connected to this repo — pushes to `main` auto-deploy.

---

## Env Vars

See `.env.example` for full reference.  
RunPod endpoint IDs are created in your [RunPod Console](https://www.runpod.io/console/serverless).  
HF token from [HuggingFace Settings](https://huggingface.co/settings/tokens).
