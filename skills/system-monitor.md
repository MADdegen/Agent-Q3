---
name: system-monitor
description: Use Kimi K2 monitor for stack health and meta-analysis
triggers: [system status, stack health, is the server up, monitor, diagnose, why is it slow, performance]
roles: [reasoner, tandem, coder]
---
The Kimi K2 monitor (`http://monitor:8003`) runs outside the local orchestration and watches every service continuously.

Endpoints to use:
- `GET /v1/monitor/status` — snapshot of all services + recent events
- `GET /v1/monitor/history?service=multimodal&limit=60` — raw 30s-interval metrics
- `GET /v1/monitor/events?limit=50` — anomalies, transitions, K2 insights
- `POST /v1/monitor/analyze` — `{query, include_metrics: true}` — asks Kimi K2 to diagnose

For any question about stack health, latency, or "why is X slow", call `/v1/monitor/analyze` and surface the K2 analysis verbatim. Do not guess from prior context.
