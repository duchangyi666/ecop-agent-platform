"""MCP server exposing web search as a tool (Tavily -> DuckDuckGo fallback).

Mounted in-process at ``/mcp/web-search``. Degrades to ``[]`` on any failure so
a missing network or key never blocks generation.
"""

from __future__ import annotations

import asyncio
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="CloudDesk-WebSearch",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def web_search(query: str, max_results: int = 3) -> list[dict]:
    """Search the public web for supplementary information.

    Tries Tavily when ``TAVILY_API_KEY`` is set, else DuckDuckGo; returns
    ``[{title, url, snippet}]`` or ``[]`` on failure.
    """
    tavily_key = os.getenv("TAVILY_API_KEY", "")
    if tavily_key:
        try:
            return await _tavily_search(query, max_results, tavily_key)
        except Exception:  # noqa: BLE001 - fall through to DuckDuckGo
            pass
    try:
        return await _duckduckgo_search(query, max_results)
    except Exception:  # noqa: BLE001 - silent degrade
        return []


async def _tavily_search(query: str, max_results: int, key: str) -> list[dict]:
    import httpx

    async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={"api_key": key, "query": query, "max_results": max_results},
        )
        resp.raise_for_status()
        data = resp.json()
        return [
            {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in data.get("results", [])[:max_results]
        ]


async def _duckduckgo_search(query: str, max_results: int) -> list[dict]:
    from duckduckgo_search import DDGS

    def _run() -> list[dict]:
        with DDGS() as ddgs:
            return [
                {"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")}
                for r in ddgs.text(query, max_results=max_results)
            ]

    return await asyncio.to_thread(_run)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(mcp.streamable_http_app(), host="0.0.0.0", port=8002)
