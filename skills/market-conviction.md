---
name: market-conviction
description: Polymarket and MAD Gambit conviction scoring for prediction market positions
triggers: [polymarket, conviction, prediction market, mad gambit, market odds, resolve market, market position, probability]
roles: [reasoner, tandem]
---
When the user asks about prediction markets, position sizing, or event probability:

1. Call `/v1/research/quant` on the research service (`http://research:8002/v1/research/quant`) with the topic.
   Returns: related Polymarket markets + parsed conviction data from CLOB orderbook.

2. Analyze the raw market data using the MAD Gambit conviction framework:
   - **Implied probability** = best ask price on CLOB
   - **Conviction score** = (volume-weighted price) × (depth asymmetry) × (time-decay factor)
   - **Edge** = your probability estimate − implied probability
   - Negative edge = no position. Positive edge = size proportional to edge magnitude.

3. Cross-reference with Kimi K2 monitor analysis (`POST http://monitor:8003/v1/monitor/analyze`) for any macro signals affecting the market.

4. Report format:
   - Market name + current odds
   - Your conviction estimate vs market
   - Edge (positive/negative/neutral)
   - Suggested action: LONG / SHORT / PASS + rationale in ≤2 sentences
   - Key unknowns that could flip the position

5. Never express conviction without a cited signal. No "I think it might" language.
