"""Web search plugin.

Tools:
  web_search(query)  — full-text search via Firecrawl Search
  scrape_url(url)    — scrape a URL via Firecrawl (falls back to plain httpx)

Requires FIRECRAWL_API_KEY. If absent, web_search is unavailable and
scrape_url falls back to a basic async httpx fetch.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import os
import re
from typing import Any

from plugins.base import PluginSpec, ToolSpec


INSTRUCTIONS = """Web search plugin:
- Use `web_search` to find current information, documentation, or anything not
  in the workspace. Always prefer searching over guessing facts.
- Use `scrape_url` to fetch the full content of a specific URL returned by search.
- Summarise scraped content; don't dump raw HTML into chat.
- Cite sources (URL) when presenting information from the web.
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(p|div|li|tr|h[1-6])>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", "", html)
    html = html_lib.unescape(html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _get_firecrawl():
    from firecrawl import Firecrawl  # type: ignore[import]
    return Firecrawl(api_key=os.environ.get("FIRECRAWL_API_KEY", ""))


# ---------------------------------------------------------------------------
# web_search — Firecrawl Search
# ---------------------------------------------------------------------------

def _firecrawl_search_sync(query: str, max_results: int) -> dict[str, Any]:
    app = _get_firecrawl()
    raw = app.search(query, limit=max_results)
    # Firecrawl v2: SearchData with .web list of SearchResultWeb objects
    items = getattr(raw, "web", None) or (raw if isinstance(raw, list) else [])
    results = []
    for r in items:
        if hasattr(r, "url"):
            results.append({
                "title": getattr(r, "title", "") or "",
                "url": r.url or "",
                "snippet": getattr(r, "description", "") or "",
            })
        elif isinstance(r, dict):
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("description", "") or r.get("markdown", "")[:300] or "",
            })
    return {"query": query, "results": results}


async def web_search(query: str, max_results: int = 6) -> dict[str, Any]:
    """Search the web using Firecrawl and return top results."""
    if not os.environ.get("FIRECRAWL_API_KEY"):
        return {"error": "FIRECRAWL_API_KEY not set", "query": query, "results": []}
    try:
        return await asyncio.to_thread(_firecrawl_search_sync, query, max_results)
    except Exception as e:
        return {"error": f"web_search failed: {e}", "query": query, "results": []}


# ---------------------------------------------------------------------------
# scrape_url — Firecrawl with async httpx fallback
# ---------------------------------------------------------------------------

def _firecrawl_scrape_sync(url: str) -> dict[str, Any]:
    app = _get_firecrawl()
    result = app.scrape(url)
    if hasattr(result, "markdown"):
        content = result.markdown or ""
        if not content and hasattr(result, "html") and result.html:
            content = _html_to_text(str(result.html))
    elif isinstance(result, dict):
        content = (
            result.get("markdown")
            or result.get("content")
            or result.get("text")
            or ""
        )
        if not content and result.get("html"):
            content = _html_to_text(str(result["html"]))
    else:
        content = ""
    return {"url": url, "content": content[:15000], "source": "firecrawl"}


async def _httpx_scrape(url: str) -> dict[str, Any]:
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CopilotBot/1.0)"}
    async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
    return {"url": url, "content": _html_to_text(resp.text)[:15000], "source": "httpx"}


async def scrape_url(url: str) -> dict[str, Any]:
    """Fetch and return the readable content of a URL."""
    if os.environ.get("FIRECRAWL_API_KEY"):
        try:
            return await asyncio.to_thread(_firecrawl_scrape_sync, url)
        except Exception as fc_err:
            try:
                result = await _httpx_scrape(url)
                result["fallback_reason"] = str(fc_err)
                return result
            except Exception as e:
                return {"error": f"scrape failed: {e}", "url": url}
    try:
        return await _httpx_scrape(url)
    except Exception as e:
        return {"error": f"scrape failed: {e}", "url": url}


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.websearch",
        name="Web Search",
        type="core",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec(name="web_search", handler=web_search),
            ToolSpec(name="scrape_url", handler=scrape_url),
        ],
        config_schema={
            "type": "object",
            "properties": {
                "max_results": {
                    "type": "integer",
                    "title": "Max search results",
                    "default": 6,
                    "minimum": 1,
                    "maximum": 20,
                }
            },
        },
    )
