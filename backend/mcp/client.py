"""Thin JSON-RPC client for calling the in-process MCP servers."""

from __future__ import annotations

import json

import httpx


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict,
    timeout: float = 30.0,
) -> list:
    """POST a ``tools/call`` JSON-RPC request and parse the text content list."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        resp = await client.post(f"{server_url}/mcp", json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    result = data.get("result", {})
    content = result.get("content", [])
    items: list = []
    for entry in content:
        text = entry.get("text", "")
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(parsed, list):
            items.extend(parsed)
        else:
            items.append(parsed)
    return items


__all__ = ["call_mcp_tool"]
