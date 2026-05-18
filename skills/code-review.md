---
name: code-review
description: Two-stage code generation with Hermes review
triggers: [review code, code review, audit code, check this code, refactor]
roles: [coder, coder_dedicated]
---
For any non-trivial code task:

1. Use the dedicated coder service (`http://coder:8001/v1/coder/review`) which automatically runs the two-stage flow:
   - Stage 1: Qwen3-Coder-30B-A3B writes the code
   - Stage 2: Hermes3 reviews for bugs, edge cases, security, idioms
2. Return both the draft AND the review.
3. If the review flags issues, output the corrected version.
4. Never add comments that explain WHAT the code does — only WHY for non-obvious decisions.
5. Default languages: TypeScript for web, Python for scripts/ML, Solidity for contracts.
