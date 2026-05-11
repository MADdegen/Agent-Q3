# Agent-Q3 — Railway Deployment Fixes

**Date:** May 11, 2026  
**Project:** MAD Gambit Agent-Q3  
**Railway Project ID:** 05b26875-629a-49e9-b599-b0bed08ac0bb

---

## Issues Resolved

### 1. **CRITICAL: Process Management Bug in start.sh**

**Problem:**
- Lines 51-68 used `exec python3 -m uvicorn ... &` which is syntactically invalid
- `exec` replaces the current shell process, so the `&` (background) operator and subsequent `ORCH_PID=$!` don't work
- The `wait $OLLAMA_PID $ORCH_PID` command fails because `ORCH_PID` is never set
- Container exits prematurely or hangs

**Fix:**
- Removed `exec` command
- Properly background the uvicorn process with `&`
- Added robust process monitoring with `kill -0` checks
- Added explicit error logging when either process dies

**Files Changed:**
- `scripts/start.sh` (lines 48-69)

---

### 2. **Railway Port Configuration Missing**

**Problem:**
- Railway provides a dynamic `$PORT` environment variable at runtime
- `Dockerfile` hardcoded `PORT=8000`, conflicting with Railway's port assignment
- `railway.toml` didn't expose PORT configuration
- Service couldn't bind to Railway's assigned port

**Fix:**
- Removed hardcoded `PORT=8000` from Dockerfile
- Added `[deploy.env]` section to railway.toml with `PORT = "${{PORT}}"`
- Updated docker-compose.yml to explicitly set `PORT: "8000"` for local dev
- Railway now correctly passes its dynamic port to the container

**Files Changed:**
- `Dockerfile` (line 34 removed)
- `railway.toml` (added lines 16-18)
- `docker-compose.yml` (added line 15)

---

### 3. **Missing Python Dependencies**

**Problem:**
- `structlog` used in main.py and router.py but not in requirements.txt
- `prometheus-fastapi-instrumentator` used in main.py but not in requirements.txt
- These cause `ModuleNotFoundError` at runtime

**Fix:**
- Added `structlog>=25.1.0` to requirements.txt
- Added `prometheus-fastapi-instrumentator>=7.0.0` to requirements.txt

**Files Changed:**
- `requirements.txt` (lines 7-8 added)

---

### 4. **Missing Import in router.py**

**Problem:**
- `StrEnum` used on line 18 but not imported
- Causes `NameError: name 'StrEnum' is not defined` at runtime

**Fix:**
- Added `from enum import StrEnum` to imports

**Files Changed:**
- `orchestrator/router.py` (line 10 added)

---

### 5. **Railway Healthcheck Timeout Too Aggressive**

**Problem:**
- First boot downloads 4GB+ models (Gemma4-E4B + Qwen3.5-4B)
- 300s (5min) healthcheck timeout insufficient
- Railway kills container before models finish pulling

**Fix:**
- Increased `healthcheckTimeout` from 300 to 600 seconds (10 minutes)
- Provides adequate time for model downloads on first deployment

**Files Changed:**
- `railway.toml` (line 8)

---

## Testing Checklist

### Local Docker
```bash
# Clean build test
docker compose down -v
docker compose build --no-cache
docker compose up

# Verify both services start
curl http://localhost:8000/health
curl http://localhost:11434/api/tags
```

### Railway Deployment
```bash
# Push fixes to main branch (auto-deploys)
git add .
git commit -m "fix: resolve Railway deployment issues - process management, port config, missing deps"
git push origin main

# Monitor Railway deployment logs
# Verify:
# 1. Both models pull successfully
# 2. Ollama server starts on :11434
# 3. Orchestrator binds to Railway's $PORT
# 4. /health endpoint returns 200 OK
# 5. No process crashes or exits
```

### API Validation
```bash
# Test auto-classify endpoint
curl -X POST https://ollama-gemma4-qwen35-pair-staging.up.railway.app/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Write a Solidity ERC-20 token"}]}'

# Test health endpoint
curl https://ollama-gemma4-qwen35-pair-staging.up.railway.app/health

# Test metrics endpoint
curl https://ollama-gemma4-qwen35-pair-staging.up.railway.app/metrics
```

---

## Deployment Notes

### First Boot (Cold Start)
- Expect 8-10 minute startup time for model downloads
- Both models cached in `/root/.ollama` volume after first pull
- Subsequent restarts take ~60-90 seconds

### Resource Requirements
- **RAM:** 8GB minimum (both Q4_K_M models loaded)
- **CPU:** 4+ cores recommended
- **Disk:** 10GB for models + base image
- **Network:** 4GB download on first boot

### Environment Variables Required
```bash
# Minimal deployment (local Ollama only)
PORT=${{PORT}}  # Railway provides this automatically
REASONER_MODEL=gemma4:e4b-instruct-q4_K_M
CODER_MODEL=qwen3.5:4b-instruct-q4_K_M

# Full deployment (HF + RunPod routing)
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RUNPOD_API_KEY=rpa_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RUNPOD_REASONER_ENDPOINT_ID=kukl55t0053lob
RUNPOD_CODER_ENDPOINT_ID=kukl55t0053lob
COMPUTE_STRATEGY=round_robin
```

---

## Architecture Validation

```
┌─────────────────────────────────────────────┐
│     Railway Container (ollama-gemma4...)    │
│                                             │
│  Process 1: Ollama Server                   │
│    PID: $OLLAMA_PID                         │
│    Port: 11434 (internal)                   │
│    Models: gemma4:e4b-q4, qwen3.5:4b-q4    │
│                                             │
│  Process 2: FastAPI Orchestrator            │
│    PID: $ORCH_PID                           │
│    Port: $PORT (Railway dynamic)            │
│    Endpoints: /v1/chat, /v1/reason,         │
│               /v1/code, /health, /metrics   │
│                                             │
│  Process Monitor: start.sh                  │
│    Restarts if either dies                  │
│    Exits with error code if crash          │
└─────────────────────────────────────────────┘
         ↓
    Railway Load Balancer
         ↓
    Public URL: ollama-gemma4-qwen35-pair-staging.up.railway.app
```

---

## Rollback Plan

If deployment fails:
1. Revert to previous commit: `git revert HEAD && git push`
2. Railway auto-redeploys previous working version
3. Check Railway logs: `railway logs --service ollama-gemma4-qwen35-pair`
4. Emergency local fallback: Use docker-compose locally until fixed

---

## Monitoring

### Key Metrics to Watch
- Container restart count (should be 0)
- Healthcheck success rate (should be 100% after warmup)
- Model pull duration (first boot only, ~8min)
- Request latency (local: <2s, HF: <5s, RunPod: <8s)
- Memory usage (should stabilize at 6-7GB)

### Logs to Monitor
```bash
# Railway CLI
railway logs --tail 100

# Look for:
# ✓ "Ollama ready after Xs"
# ✓ "Both models loaded ✓"
# ✓ "Launching Agent-Q3 Orchestrator on port XXXX"
# ✓ "Application startup complete"
```

---

## Next Steps

1. **Deploy to Railway** — Push to main branch
2. **Monitor first boot** — Watch logs for successful model pulls
3. **Test all endpoints** — /health, /v1/chat, /v1/reason, /v1/code, /v1/tandem
4. **Load test** — Verify concurrent request handling
5. **Document API** — Update MAD Gambit docs with new endpoint

---

**Status:** ✅ All fixes implemented and tested locally  
**Ready for deployment:** YES  
**Estimated downtime:** 10-12 minutes (first boot model download)
