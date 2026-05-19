---
name: doc-lookup
description: Domain-scoped documentation lookup via Perplexity doc_lookup and Jina Reader
triggers: [documentation, api reference, docs, library guide, how to use, official docs, api docs, read the docs, rtfd]
roles: [coder, coder_dedicated, reasoner]
---
When the user needs official documentation for a library, API, or framework:

1. **Primary — Perplexity doc_lookup**: Use when `PERPLEXITY_API_KEY` is set. Scopes the search to official documentation domains only. Invoke via the research service:
   - `POST http://research:8002/v1/research/deep` with `{"query": "<library> <question>", "use_perplexity": true, "use_exa": false, "use_tavily": false, "use_free": false, "domains": ["docs.<lib>.org", "pkg.go.dev", "docs.rs", "<lib>.readthedocs.io"]}`

2. **Fallback — Jina Reader scrape**: If Perplexity is unavailable, scrape the docs page directly:
   - `POST http://research:8002/v1/research/scrape` with `{"url": "<docs_url>", "max_chars": 8000}`

3. **Source priority by ecosystem:**
   - Python: `docs.python.org`, `<lib>.readthedocs.io`, `pypi.org/project/<lib>`
   - JS/TS: `<lib>.dev`, `npmjs.com/package/<lib>`, `typedoc` sites
   - Solidity: `docs.soliditylang.org`, `docs.openzeppelin.com`, `book.getfoundry.sh`
   - Rust: `docs.rs/<crate>`, `doc.rust-lang.org`
   - Go: `pkg.go.dev/<module>`

4. Return: exact function signatures, parameters, return types, and the **minimum working example** from the docs. No paraphrasing — quote the canonical source.
