# Deep Research Skill — Agent-Q3

## Trigger
Activate when user needs: research, investigation, deep dive, current events, academic papers, multi-source synthesis.

## Research cascade (cost-optimized)

### Tier 1 — Free (always runs first)
1. free_search.py — DuckDuckGo + Jina + ArXiv + Wikipedia + GitHub
2. searxng — Railway internal meta-search (70+ engines, zero cost)

### Tier 2 — Paid APIs (if Tier 1 insufficient)
3. web_search.py — Exa -> Tavily -> Brave (auto-fallback)
4. perplexity_search.py — sonar / sonar-pro

### Tier 3 — Deep research (comprehensive multi-step)
5. Perplexity sonar-deep-research — multi-step, 128K ctx, full citations

## MCP tool call
deep_research { "query": "...", "model": "sonar-deep-research" }

## Model routing
- Short factual -> Qwen3-8B-Kimi (fast)
- Multi-step analysis -> QwQ-32B (131K ctx)
- Vision/multimodal -> Qwen2.5-VL-32B

## Output format
1. Summary (3-5 sentences)
2. Key findings (numbered)
3. Sources with URLs
4. Confidence level (High/Medium/Low)
5. Recommended follow-up queries
