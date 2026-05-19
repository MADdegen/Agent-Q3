---
name: code-search
description: Semantic code search, GitHub examples, PyPI/npm package intelligence
triggers: [search code, find implementation, github example, similar code, package version, dependency, npm, pypi, library, find a library]
roles: [coder, coder_dedicated, tandem]
---
For implementation reference, dependency analysis, or package intelligence:

**Code search:**
- Call `POST http://mcp-bridge:8004/mcp/call` with `{"server": "arxiv-mcp", "tool": "search", "args": {"query": "..."}}` for algorithm papers.
- Call `GET http://research:8002/v1/research/scrape` with a GitHub search URL for code examples.
- Use the `code_search` tool in `orchestrator/tools/web_search.py` via the research service's Exa/Tavily backends — it is pre-configured to bias toward code repositories.

**Package lookup (PyPI / npm):**
- Call `POST http://mcp-bridge:8004/mcp/call` with:
  ```json
  {"server": "smithery-search", "tool": "searchPackages", "args": {"query": "<package>", "ecosystem": "pypi|npm"}}
  ```
- For version history, license, and dependency tree: add `cache_ttl_secs: 3600` (package metadata is stable).

**When to stop searching and just write the code:**
- If you find ≥1 canonical reference (docs page, GitHub repo, npm/PyPI page), stop searching.
- If you've done 2 searches and found nothing useful, write the implementation from first principles.
- Never search for boilerplate that you can generate correctly from memory (React hooks, Python stdlib, basic Solidity patterns).
