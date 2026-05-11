"""
free_search.py — Zero-API-key search tools hardcoded into Agent-Q3.
No secrets needed. Both agents use these as first-pass search.

Tools:
  1. DuckDuckGo    — instant answers + web search (duckduckgo-search lib)
  2. Jina Reader   — web page extraction via reader.jina.ai (free tier, no key)
  3. ArXiv         — academic paper search (official free API)
  4. Wikipedia     — encyclopedia lookup (free REST API)
  5. GitHub Search — code/repo/issue search (uses existing GH_PAT)
  6. PyPI / npm    — package info lookup (public registries, no auth)

Routing:
  - Coder agent   → GitHub Search + PyPI/npm + Jina (for docs)
  - Reasoner agent → DuckDuckGo + ArXiv + Wikipedia + Jina (for deep research)
"""
import httpx
import os
from typing import Optional

# ─── 1. DuckDuckGo ────────────────────────────────────────────────────────────

async def search_duckduckgo(
    query: str,
    max_results: int = 10,
    region: str = "wt-wt",
    safesearch: str = "off",
) -> list[dict]:
    """
    DuckDuckGo instant search — no API key, no rate limits enforced.
    Uses the DDG HTML endpoint parsed as JSON via the duckduckgo_search lib.
    Falls back to direct HTTP if lib unavailable.
    """
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region=region, safesearch=safesearch, max_results=max_results):
                results.append({
                    "title":   r.get("title",""),
                    "url":     r.get("href",""),
                    "snippet": r.get("body","")[:400],
                    "source":  "duckduckgo",
                })
        return results
    except ImportError:
        # Fallback: DDG instant answers API
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.duckduckgo.com/",
                    params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1},
                    headers={"User-Agent": "Agent-Q3/1.0"},
                )
                if r.status_code == 200:
                    data = r.json()
                    results = []
                    for topic in data.get("RelatedTopics", [])[:max_results]:
                        if "Text" in topic:
                            results.append({
                                "title":   topic.get("Text","")[:80],
                                "url":     topic.get("FirstURL",""),
                                "snippet": topic.get("Text","")[:400],
                                "source":  "duckduckgo",
                            })
                    return results
        except Exception:
            pass
    return []


# ─── 2. Jina Reader (free web page extraction) ────────────────────────────────

async def jina_read(url: str, timeout: int = 30) -> dict:
    """
    Jina Reader — extracts clean markdown from any URL.
    Endpoint: https://r.jina.ai/{url}
    Free tier: generous rate limit, no key needed.
    Best for: reading docs, blog posts, GitHub READMEs, news articles.
    """
    jina_url = f"https://r.jina.ai/{url}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(
                jina_url,
                headers={
                    "Accept": "text/plain",
                    "User-Agent": "Agent-Q3/1.0",
                    "X-Return-Format": "markdown",
                },
                follow_redirects=True,
            )
            if r.status_code == 200:
                content = r.text
                return {
                    "url":     url,
                    "content": content[:8000],  # 8K chars — enough for context
                    "length":  len(content),
                    "source":  "jina_reader",
                }
    except Exception as e:
        return {"url": url, "error": str(e), "source": "jina_reader"}
    return {"url": url, "error": f"HTTP {r.status_code}", "source": "jina_reader"}


async def jina_search(query: str, max_results: int = 5) -> list[dict]:
    """
    Jina Search — AI-powered web search via s.jina.ai (free, no key).
    Returns structured results with full page content.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"https://s.jina.ai/{httpx.URL(query)}",
                headers={
                    "Accept": "application/json",
                    "X-Return-Format": "markdown",
                },
            )
            if r.status_code == 200:
                data = r.json() if r.headers.get("content-type","").startswith("application/json") else {}
                results = data.get("data", [])
                return [{
                    "title":   item.get("title",""),
                    "url":     item.get("url",""),
                    "content": item.get("content","")[:1000],
                    "source":  "jina_search",
                } for item in results[:max_results]]
    except Exception:
        pass
    return []


# ─── 3. ArXiv (academic papers — free official API) ───────────────────────────

async def search_arxiv(
    query: str,
    max_results: int = 8,
    sort_by: str = "relevance",  # relevance | lastUpdatedDate | submittedDate
) -> list[dict]:
    """
    ArXiv API — free academic paper search.
    No key needed. Official API rate limit: 3 req/sec.
    Reasoner uses this for deep research, literature review, citation lookup.
    """
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                "https://export.arxiv.org/api/query",
                params={
                    "search_query": f"all:{query}",
                    "start": 0,
                    "max_results": max_results,
                    "sortBy": sort_by,
                    "sortOrder": "descending",
                },
            )
            if r.status_code == 200:
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.text)
                ns = {"atom": "http://www.w3.org/2005/Atom"}
                results = []
                for entry in root.findall("atom:entry", ns):
                    def txt(tag):
                        el = entry.find(tag, ns)
                        return el.text.strip() if el is not None and el.text else ""
                    authors = [
                        a.find("atom:name", ns).text
                        for a in entry.findall("atom:author", ns)
                        if a.find("atom:name", ns) is not None
                    ]
                    arxiv_id = txt("atom:id").split("/abs/")[-1]
                    results.append({
                        "title":    txt("atom:title").replace("
","").strip(),
                        "authors":  authors[:3],
                        "summary":  txt("atom:summary")[:500],
                        "url":      f"https://arxiv.org/abs/{arxiv_id}",
                        "pdf":      f"https://arxiv.org/pdf/{arxiv_id}",
                        "published": txt("atom:published")[:10],
                        "source":   "arxiv",
                    })
                return results
    except Exception as e:
        return [{"error": str(e), "source": "arxiv"}]
    return []


# ─── 4. Wikipedia (free REST API) ────────────────────────────────────────────

async def search_wikipedia(
    query: str,
    language: str = "en",
    max_results: int = 3,
    extract_chars: int = 1500,
) -> list[dict]:
    """
    Wikipedia REST API — free, no key, 200 req/sec limit.
    Returns article summaries + extract. Used by Reasoner for background context.
    """
    results = []
    try:
        base = f"https://{language}.wikipedia.org/w/api.php"
        async with httpx.AsyncClient(timeout=15) as client:
            # Search
            sr = await client.get(base, params={
                "action": "query", "format": "json",
                "list": "search", "srsearch": query,
                "srlimit": max_results, "utf8": 1,
            })
            if sr.status_code == 200:
                items = sr.json().get("query",{}).get("search",[])
                for item in items[:max_results]:
                    title = item["title"]
                    # Get extract
                    er = await client.get(base, params={
                        "action": "query", "format": "json",
                        "titles": title, "prop": "extracts|info",
                        "exintro": 1, "exchars": extract_chars,
                        "inprop": "url", "utf8": 1,
                    })
                    if er.status_code == 200:
                        pages = er.json().get("query",{}).get("pages",{})
                        for page in pages.values():
                            import re
                            extract = re.sub(r"<[^>]+>","", page.get("extract",""))
                            results.append({
                                "title":   page.get("title",""),
                                "extract": extract.strip()[:extract_chars],
                                "url":     page.get("fullurl", f"https://{language}.wikipedia.org/wiki/{title.replace(' ','_')}"),
                                "source":  "wikipedia",
                            })
    except Exception as e:
        results.append({"error": str(e), "source": "wikipedia"})
    return results


# ─── 5. GitHub Search (uses existing PAT) ────────────────────────────────────

async def search_github(
    query: str,
    search_type: str = "code",  # code | repositories | issues | users | commits
    language: Optional[str] = None,
    max_results: int = 10,
) -> list[dict]:
    """
    GitHub Search API — uses existing GH_PAT from env.
    No extra key needed. Coder agent uses this for:
    - code examples and patterns
    - finding repos to reference
    - looking up issues for known bugs
    """
    token = os.environ.get("GITHUB_PAT","") or os.environ.get("GH_TOKEN","")
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    q = query
    if language:
        q += f" language:{language}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(
                f"https://api.github.com/search/{search_type}",
                headers=headers,
                params={"q": q, "per_page": max_results, "sort": "stars", "order": "desc"},
            )
            if r.status_code == 200:
                items = r.json().get("items", [])
                results = []
                for item in items[:max_results]:
                    if search_type == "repositories":
                        results.append({
                            "name":        item.get("full_name",""),
                            "description": item.get("description","")[:200],
                            "url":         item.get("html_url",""),
                            "stars":       item.get("stargazers_count",0),
                            "language":    item.get("language",""),
                            "source":      "github",
                        })
                    elif search_type == "code":
                        results.append({
                            "name":    item.get("name",""),
                            "path":    item.get("path",""),
                            "repo":    item.get("repository",{}).get("full_name",""),
                            "url":     item.get("html_url",""),
                            "source":  "github",
                        })
                    else:
                        results.append({
                            "title": item.get("title", item.get("name","?")),
                            "url":   item.get("html_url",""),
                            "source": "github",
                        })
                return results
    except Exception as e:
        return [{"error": str(e), "source": "github"}]
    return []


# ─── 6. PyPI + npm (package registries — no auth) ────────────────────────────

async def lookup_pypi(package: str) -> dict:
    """PyPI package info — free, no key. Coder uses for dependency research."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://pypi.org/pypi/{package}/json")
            if r.status_code == 200:
                info = r.json()["info"]
                return {
                    "name":        info.get("name"),
                    "version":     info.get("version"),
                    "summary":     info.get("summary",""),
                    "home_page":   info.get("home_page",""),
                    "license":     info.get("license",""),
                    "requires":    info.get("requires_dist",[])[: 10],
                    "source":      "pypi",
                }
    except Exception as e:
        return {"error": str(e), "package": package, "source": "pypi"}
    return {"error": "not found", "package": package, "source": "pypi"}


async def lookup_npm(package: str) -> dict:
    """npm package info — free, no key. Coder uses for JS/TS dependency research."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://registry.npmjs.org/{package}/latest")
            if r.status_code == 200:
                data = r.json()
                return {
                    "name":        data.get("name"),
                    "version":     data.get("version"),
                    "description": data.get("description",""),
                    "homepage":    data.get("homepage",""),
                    "license":     data.get("license",""),
                    "dependencies": list((data.get("dependencies") or {}).keys())[:10],
                    "source":      "npm",
                }
    except Exception as e:
        return {"error": str(e), "package": package, "source": "npm"}
    return {"error": "not found", "package": package, "source": "npm"}


# ─── Combined smart search dispatcher ────────────────────────────────────────

async def smart_search(
    query: str,
    role: str = "auto",  # auto | reasoner | coder
    max_results: int = 8,
) -> dict:
    """
    Smart search dispatcher — routes to best free tools based on agent role.

    Reasoner → DuckDuckGo + Wikipedia + ArXiv (research stack)
    Coder    → DuckDuckGo + GitHub Search + Jina (code stack)
    Auto     → classifies from query content
    """
    if role == "auto":
        code_signals = ["function","class","import","install","pip","npm","error","bug","api","sdk","library","package","python","typescript","solidity","rust","go","code"]
        role = "coder" if any(s in query.lower() for s in code_signals) else "reasoner"

    results: dict = {"query": query, "role": role, "sources": {}}

    if role == "coder":
        # Code-focused: GitHub + DDG + Jina
        ddg = await search_duckduckgo(query, max_results=max_results)
        gh  = await search_github(query, search_type="repositories", max_results=5)
        results["sources"]["duckduckgo"] = ddg
        results["sources"]["github"]     = gh

    else:
        # Research-focused: DDG + Wikipedia + ArXiv (if academic signals)
        ddg  = await search_duckduckgo(query, max_results=max_results)
        wiki = await search_wikipedia(query, max_results=2)
        results["sources"]["duckduckgo"] = ddg
        results["sources"]["wikipedia"]  = wiki
        academic_signals = ["research","paper","study","analysis","model","algorithm","dataset","predict","market","conviction"]
        if any(s in query.lower() for s in academic_signals):
            arxiv = await search_arxiv(query, max_results=4)
            results["sources"]["arxiv"] = arxiv

    results["total"] = sum(len(v) for v in results["sources"].values())
    return results
