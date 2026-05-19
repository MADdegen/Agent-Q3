---
name: package-intel
description: PyPI and npm package metadata, security, version history, dependency analysis
triggers: [pypi, npm, package, dependency, version, install, requirements, package.json, is it safe, latest version, alternatives to]
roles: [coder, coder_dedicated]
---
For any package/dependency question:

**Quick lookup (no API key needed):**
- PyPI: `POST http://research:8002/v1/research/scrape` with `{"url": "https://pypi.org/pypi/<package>/json"}` — returns maintainer, license, latest version, release history, dependencies
- npm: `POST http://research:8002/v1/research/scrape` with `{"url": "https://registry.npmjs.org/<package>"}` — same fields

**Security check:**
- For any production dependency, check: `https://osv.dev/v1/query` (Google OSV) for known CVEs.
- Red flags: 0 maintainers, last release >2 years, no source link, <100 weekly downloads.

**Finding alternatives:**
- `POST http://mcp-bridge:8004/mcp/call` with `{"server": "smithery-search", "tool": "search", "args": {"query": "alternative to <package> <ecosystem>"}}`
- Cross-reference with GitHub Stars and download trends.

**Decision criteria:**
- Prefer packages that are: actively maintained (commit in last 6 months), >1K weekly downloads, MIT/Apache/BSD license, typed.
- For ML/AI packages: prefer ones on HF Hub (check `https://huggingface.co/docs/<package>`).

Output format: package name, version, license, weekly downloads, last release date, CVE status, recommendation (USE / USE_WITH_CAUTION / AVOID + one-sentence reason).
