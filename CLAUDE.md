# Agent-Q3 — CLAUDE.md

## Project identity
Agent-Q3 is a self-hosted triple-model AI agent stack deployed on Railway.
Owner: Nick (MADdegen) — Founder of MAD Gambit.

## Model stack
- Reasoner: hf.co/unsloth/Qwen2.5-VL-32B-Instruct-GGUF:Q4_K_M (multimodal, deep reasoning)
- Support:  hf.co/TeichAI/Qwen3-8B-Kimi-K2-Thinking-Distill-GGUF:Q4_K_M (hybrid, punches at 16B)
- Coder:    hf.co/unsloth/QwQ-32B-GGUF:Q4_K_M (131K ctx, deep research + coding)

All models: Unsloth Dynamic 2.0 / Q4_K_M GGUF format.

## Tech stack
- Compute: Railway (Ollama on GPU volume) -> HuggingFace Router -> RunPod -> OpenRouter
- API: FastAPI + uvicorn on port 8000
- Memory: Redis (short-term 24h) + Postgres pgvector 384-dim (long-term)
- Search: DuckDuckGo + Jina + ArXiv + SearXNG + Exa + Tavily + Perplexity
- Claude Cowork: MCP endpoint at /cowork/mcp, memory at /cowork/memory/*

## Canonical numbers (NEVER change)
- Platform fee: 1.88%
- Community profit share: 28.8% (display as 28%)
- Creator revenue share: 40%
- Seed raise: $1-2M at $12M pre-money valuation

## Repo structure
- orchestrator/        FastAPI app (main.py, router.py, config.py, models.py)
- orchestrator/tools/  Search + memory tools
- orchestrator/cowork_ui.py  Claude Cowork MCP + memory endpoints
- skills/              Memory + deep research skill definitions
- config/              engine_config.yaml
- scripts/start.sh     Ollama model pull + serve
- supabase/migrations/ DB schema (pgvector, memory, quota, tasks)
- .mcp.json            MCP server registry (12 servers)

## Rules
1. Always use exact model:tag strings — never short names
2. Never use gemma4 or qwen3.5 names — those are the OLD stack
3. pull_model() uses exact grep-qx match — do not revert to base name grep
4. Memory saves go to /cowork/memory/save — not to files
5. Deep research routes through the tier cascade in skills/deep_research_skill.md
6. Claude Cowork connects via /cowork/mcp — all 8 tools exposed

## From My-Claude toolkit (The-MDC org)
- Hooks: .claude/hooks/ from The-MDC/claude-code-hooks
- Best practices: patterns from The-MDC/claude-code-best-practice
- Multi-agent: orchestration patterns from The-MDC/claude-code-multi-agent-orchestrartion
- Skills: Alchemy agent skills from The-MDC/skills
