"""Web search plugin.

Tools:
  web_search(query)  — full-text search via DuckDuckGo, returns titles/URLs/snippets
  scrape_url(url)    — scrape a URL via Firecrawl (falls back to plain httpx)

Firecrawl is used when FIRECRAWL_API_KEY is set; otherwise scraping falls back
to a basic httpx fetch + html→text strip.
"""

from __future__ import annotations

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
# web_search — DuckDuckGo
# ---------------------------------------------------------------------------

def web_search(query: str, max_results: int = 6) -> dict[str, Any]:
    """Search the web using DuckDuckGo and return top results."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return {"query": query, "results": results}
    except Exception as e:
        return {"error": f"web_search failed: {e}", "query": query, "results": []}


# ---------------------------------------------------------------------------
# scrape_url — Firecrawl with httpx fallback
# ---------------------------------------------------------------------------

def _firecrawl_scrape(url: str) -> dict[str, Any]:
    from firecrawl import Firecrawl  # type: ignore[import]
    api_key = os.environ.get("FIRECRAWL_API_KEY", "")
    app = Firecrawl(api_key=api_key)
    result = app.scrape(url)
    # firecrawl >= v2 returns a Document object; older versions return a dict
    if hasattr(result, "markdown"):
        markdown = result.markdown or ""
        if not markdown and hasattr(result, "html") and result.html:
            markdown = _html_to_text(str(result.html))
    elif isinstance(result, dict):
        markdown = (
            result.get("markdown")
            or result.get("content")
            or result.get("text")
            or ""
        )
        if not markdown and result.get("html"):
            markdown = _html_to_text(str(result["html"]))
    else:
        markdown = ""
    return {
        "url": url,
        "content": markdown[:8000],
        "source": "firecrawl",
    }


def _httpx_scrape(url: str) -> dict[str, Any]:
    import httpx
    headers = {"User-Agent": "Mozilla/5.0 (compatible; CopilotBot/1.0)"}
    resp = httpx.get(url, headers=headers, follow_redirects=True, timeout=15)
    resp.raise_for_status()
    text = _html_to_text(resp.text)
    return {
        "url": url,
        "content": text[:8000],
        "source": "httpx",
    }


def _html_to_text(html: str) -> str:
    # Strip scripts/styles then tags
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def scrape_url(url: str) -> dict[str, Any]:
    """Fetch and return the readable content of a URL.

    Uses Firecrawl when FIRECRAWL_API_KEY is set, otherwise falls back to a
    plain HTTP fetch.
    """
    if os.environ.get("FIRECRAWL_API_KEY"):
        try:
            return _firecrawl_scrape(url)
        except Exception as fc_err:
            # Firecrawl failed — fall back to httpx
            try:
                result = _httpx_scrape(url)
                result["fallback_reason"] = str(fc_err)
                return result
            except Exception as e:
                return {"error": f"scrape failed: {e}", "url": url}
    else:
        try:
            return _httpx_scrape(url)
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
