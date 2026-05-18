---
name: deep-research
description: Multi-source deep research synthesis
triggers: [research, investigate, sources, deep dive, analyze deeply, citations]
roles: [reasoner, coder, tandem]
---
When the user requests research or investigation:

1. Query the research service (`http://research:8002/v1/research/deep`) first with all available providers (Perplexity, Exa, Tavily, free fallback).
2. If the topic is finance, prediction, or event-driven, also query `/v1/research/quant` for Polymarket conviction signals.
3. Synthesize findings in this order:
   - **Thesis** (one sentence)
   - **Evidence** (numbered, with inline source citations)
   - **Counterpoints / source conflicts**
   - **Unknowns**
4. Cite sources inline with [n] markers and end with a numbered source list.
5. Never use filler words like "leverage", "synergy", "unlock", "game-changing".
