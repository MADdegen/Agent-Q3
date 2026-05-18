"""
Agent-Q3 — Kimi K2 Always-On Monitor.

Runs in its own container, outside the local Ollama orchestration. Polls every
service's /health every 30s, stores a rolling hour of metrics, and uses
Kimi K2 (moonshotai/kimi-k2 via OpenRouter cloud) to analyze anomalies and
answer meta-questions about the stack.

Kimi K2 is called via direct HTTP — NOT through the local compute router —
to keep this monitor independent of the very services it watches.

Endpoints:
  GET  /                       — service info
  GET  /health                 — monitor's own health + Kimi K2 reachability
  GET  /v1/monitor/status      — current state of all watched services
  GET  /v1/monitor/history     — raw metrics history per service
  GET  /v1/monitor/events      — recent events (transitions, anomalies, K2 insights)
  POST /v1/monitor/analyze     — send a query + snapshot to Kimi K2, return analysis
  WS   /ws/live                — real-time event stream
"""

import asyncio
import time
from collections import deque
from contextlib import asynccontextmanager
from typing import Any

import httpx
import structlog
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel

from ..config import settings
from ..memory import memory

log = structlog.get_logger(__name__)


MONITOR_SYSTEM = """You are the Agent-Q3 System Monitor powered by Kimi K2.
Your role: watch the multi-container AI stack and produce smart, actionable insights.

Stack you monitor:
- multimodal :8000 — Kimi-VL-A3B + Qwen3-48B-Savant + Qwopus + Hermes tandem
- coder      :8001 — Qwen3-Coder-30B-A3B dedicated + Hermes review
- research   :8002 — Perplexity / Exa / Tavily / Free / Polymarket synthesis
- mcp-bridge :8004 — unified MCP server gateway
- ollama     :11434 — shared model server, 5 models hot

When given metrics: identify patterns, root causes, and predict issues before they happen.
Be specific. Use latency numbers. Name the exact service and model. No filler.
"""


def _parse_targets() -> dict[str, str]:
    """Parse MONITOR_TARGETS env-style csv: 'http://multimodal:8000,http://ollama:11434'."""
    raw = settings.monitor_targets
    parsed: dict[str, str] = {}
    for item in raw.split(","):
        item = item.strip().rstrip("/")
        if not item:
            continue
        # extract host-without-port as the friendly name
        host = item.replace("http://", "").replace("https://", "").split(":")[0]
        parsed[host] = item
    return parsed


class MonitorState:
    """In-memory rolling metrics + WebSocket pubsub."""
    def __init__(self):
        # 120 readings × 30s = 1 hour history per service
        self.metrics: dict[str, deque] = {}
        self.events: deque = deque(maxlen=500)
        self.subscribers: set[asyncio.Queue] = set()
        self.last_k2_analysis_ts: dict[str, float] = {}  # per-service rate limit
        self.started_at: float = time.time()

    def reading(self, name: str) -> deque:
        if name not in self.metrics:
            self.metrics[name] = deque(maxlen=120)
        return self.metrics[name]

    async def emit(self, event: dict) -> None:
        event = {"ts": time.time(), **event}
        self.events.appendleft(event)
        try:
            await memory.log_event("monitor", event)
        except Exception:
            pass
        for q in list(self.subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def last_state(self, name: str) -> str | None:
        d = self.metrics.get(name)
        if not d:
            return None
        return d[-1].get("status")


state = MonitorState()


async def _poll_one(name: str, base_url: str) -> dict:
    """Hit /health (or / for ollama) and return a normalized reading."""
    health_path = "/" if "ollama" in base_url else "/health"
    started = time.time()
    record: dict[str, Any] = {
        "service": name,
        "url": base_url,
        "ts": started,
        "status": "down",
        "latency_ms": None,
        "detail": None,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{base_url}{health_path}")
            record["latency_ms"] = round((time.time() - started) * 1000, 1)
            if r.status_code == 200:
                record["status"] = "up"
                try:
                    record["detail"] = r.json()
                except Exception:
                    record["detail"] = {"raw": r.text[:200]}
            else:
                record["status"] = "degraded"
                record["detail"] = {"http_status": r.status_code}
    except Exception as e:
        record["latency_ms"] = round((time.time() - started) * 1000, 1)
        record["detail"] = {"error": str(e)}
    return record


async def _poll_loop():
    """Background loop — polls every service every N seconds."""
    targets = _parse_targets()
    log.info("monitor poll loop starting",
             targets=list(targets.keys()),
             interval=settings.kimi_k2_poll_interval_secs)
    while True:
        try:
            results = await asyncio.gather(
                *[_poll_one(n, u) for n, u in targets.items()],
                return_exceptions=True,
            )
            for record in results:
                if isinstance(record, Exception):
                    log.warning("poll exception", error=str(record))
                    continue
                name = record["service"]
                prev_status = state.last_state(name)
                state.reading(name).append(record)

                # Transition event
                if prev_status and prev_status != record["status"]:
                    await state.emit({
                        "kind": "transition",
                        "service": name,
                        "from": prev_status,
                        "to": record["status"],
                        "latency_ms": record["latency_ms"],
                    })
                    # On down/degraded → trigger Kimi K2 analysis (rate-limited 5min/svc)
                    if record["status"] != "up" and settings.has_kimi_k2():
                        last = state.last_k2_analysis_ts.get(name, 0)
                        if time.time() - last > 300:
                            state.last_k2_analysis_ts[name] = time.time()
                            asyncio.create_task(_k2_anomaly_analysis(name, record))
                # Latency anomaly
                elif record["latency_ms"] and record["latency_ms"] > 10000:
                    await state.emit({
                        "kind": "slow_response",
                        "service": name,
                        "latency_ms": record["latency_ms"],
                    })
        except Exception as e:
            log.error("poll loop iteration failed", error=str(e))

        await asyncio.sleep(settings.kimi_k2_poll_interval_secs)


async def _call_kimi_k2(messages: list[dict], temperature: float = 0.4,
                       max_tokens: int = 1024) -> dict:
    """
    Kimi K2 inference — tries Ollama Cloud first (kimi-k2:1t-cloud via signed-in
    ollama instance), then falls back to OpenRouter (moonshotai/kimi-k2).
    Bypasses the local router — monitor stays independent of services it watches.
    """
    # ── 1. Ollama Cloud (requires `ollama signin` on the ollama container) ──
    if settings.ollama_cloud_enabled:
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    f"{settings.ollama_base_url}/api/chat",
                    json={
                        "model": settings.kimi_k2_model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,
                        },
                    },
                )
                r.raise_for_status()
                raw = r.json()
                return {
                    "choices": [{
                        "message": raw.get("message", {"role": "assistant", "content": ""}),
                    }],
                    "model": settings.kimi_k2_model,
                    "_via": "ollama-cloud",
                    "usage": {
                        "prompt_tokens": raw.get("prompt_eval_count"),
                        "completion_tokens": raw.get("eval_count"),
                    },
                }
        except Exception as e:
            log.warning("ollama-cloud kimi-k2 failed, falling back to openrouter",
                       error=str(e))

    # ── 2. OpenRouter fallback ──────────────────────────────────────────────
    if not settings.openrouter_api_key:
        raise RuntimeError("Kimi K2 unavailable: ollama-cloud failed AND OPENROUTER_API_KEY unset")
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "HTTP-Referer": "https://github.com/MADdegen/Agent-Q3",
        "X-Title": "Agent-Q3-Monitor",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.kimi_k2_fallback_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{settings.kimi_k2_api_url}/chat/completions",
                              headers=headers, json=payload)
        r.raise_for_status()
        out = r.json()
        out["_via"] = "openrouter"
        return out


async def _k2_anomaly_analysis(service: str, record: dict) -> None:
    """Triggered when a service transitions to down/degraded."""
    try:
        snapshot = _build_snapshot()
        resp = await _call_kimi_k2([
            {"role": "system", "content": MONITOR_SYSTEM},
            {"role": "user", "content":
                f"ANOMALY: service `{service}` is {record['status']}.\n\n"
                f"Latest reading: {record}\n\n"
                f"Stack snapshot:\n{snapshot}\n\n"
                f"Diagnose the most likely cause in ≤4 bullets. "
                f"Suggest the single highest-leverage check the operator should run first."},
        ], temperature=0.3, max_tokens=512)
        msg = resp["choices"][0]["message"]["content"]
        await state.emit({
            "kind": "k2_insight",
            "service": service,
            "trigger": "anomaly",
            "analysis": msg,
        })
    except Exception as e:
        log.warning("kimi K2 anomaly analysis failed", error=str(e))


def _build_snapshot() -> dict:
    snap = {}
    for name, dq in state.metrics.items():
        if not dq:
            continue
        latest = dq[-1]
        latencies = [r["latency_ms"] for r in dq if r.get("latency_ms")]
        up_count = sum(1 for r in dq if r.get("status") == "up")
        snap[name] = {
            "current_status": latest["status"],
            "current_latency_ms": latest["latency_ms"],
            "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else None,
            "uptime_pct": round(100.0 * up_count / len(dq), 2),
            "samples": len(dq),
        }
    return snap


# ── FastAPI app ──────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Monitor starting",
             kimi_k2_model=settings.kimi_k2_model,
             k2_enabled=settings.has_kimi_k2(),
             targets=_parse_targets())
    await memory.connect()
    poll_task = asyncio.create_task(_poll_loop())
    yield
    poll_task.cancel()
    await memory.close()
    log.info("Monitor shutting down")


app = FastAPI(
    title="Agent-Q3 Monitor",
    description="Kimi K2 always-on system monitor (cloud, outside local orchestration)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


class AnalyzeRequest(BaseModel):
    query: str
    include_metrics: bool = True


@app.get("/")
async def root():
    return {
        "service": "Agent-Q3 Monitor",
        "kimi_k2_model": settings.kimi_k2_model,
        "kimi_k2_enabled": settings.has_kimi_k2(),
        "poll_interval_secs": settings.kimi_k2_poll_interval_secs,
        "targets": _parse_targets(),
        "uptime_secs": round(time.time() - state.started_at, 1),
    }


@app.get("/health")
async def health():
    k2_ok = False
    if settings.has_kimi_k2():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(f"{settings.kimi_k2_api_url}/models",
                    headers={"Authorization": f"Bearer {settings.openrouter_api_key}"})
                k2_ok = r.status_code == 200
        except Exception:
            pass
    return {
        "status": "ok",
        "kimi_k2_reachable": k2_ok,
        "memory_backend": memory.backend,
        "services_tracked": list(state.metrics.keys()),
        "uptime_secs": round(time.time() - state.started_at, 1),
    }


@app.get("/v1/monitor/status")
async def status():
    return {
        "snapshot": _build_snapshot(),
        "events_recent": list(state.events)[:10],
    }


@app.get("/v1/monitor/history")
async def history(service: str, limit: int = 60):
    dq = state.metrics.get(service)
    if not dq:
        raise HTTPException(404, detail=f"no metrics for service '{service}'")
    return {"service": service, "history": list(dq)[-limit:]}


@app.get("/v1/monitor/events")
async def events(limit: int = 50):
    return {"events": list(state.events)[:limit]}


@app.post("/v1/monitor/analyze")
async def analyze(req: AnalyzeRequest):
    if not settings.has_kimi_k2():
        raise HTTPException(503, detail="OPENROUTER_API_KEY not set — Kimi K2 disabled")
    user_msg = req.query
    if req.include_metrics:
        user_msg += f"\n\nCurrent stack snapshot:\n{_build_snapshot()}"
        user_msg += f"\n\nLast 10 events:\n{list(state.events)[:10]}"
    try:
        resp = await _call_kimi_k2([
            {"role": "system", "content": MONITOR_SYSTEM},
            {"role": "user", "content": user_msg},
        ], temperature=0.4, max_tokens=2048)
    except Exception as e:
        raise HTTPException(503, detail=f"Kimi K2 call failed: {e}")
    content = resp["choices"][0]["message"]["content"]
    await state.emit({"kind": "k2_insight", "trigger": "user_query",
                     "query": req.query[:200], "analysis": content[:200]})
    return {
        "model": settings.kimi_k2_model,
        "analysis": content,
        "usage": resp.get("usage", {}),
    }


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket):
    await ws.accept()
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    state.subscribers.add(q)
    try:
        await ws.send_json({"kind": "hello",
                            "tracked": list(state.metrics.keys()),
                            "uptime_secs": round(time.time() - state.started_at, 1)})
        while True:
            event = await q.get()
            await ws.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        state.subscribers.discard(q)
