from __future__ import annotations

import pytest


def _tool_names(mcp_server) -> set[str]:
    tools = mcp_server._tool_manager.list_tools()
    return {t.name for t in tools}


def test_knowledge_mcp_server_registers_search_tool() -> None:
    from backend.mcp.knowledge_base_server import mcp as kb_mcp

    assert "search_knowledge" in _tool_names(kb_mcp)


def test_web_search_mcp_server_registers_search_tool() -> None:
    from backend.mcp.web_search_server import mcp as ws_mcp

    assert "web_search" in _tool_names(ws_mcp)


@pytest.mark.asyncio
async def test_web_search_degrades_to_empty_list_offline(monkeypatch) -> None:
    import backend.mcp.web_search_server as ws

    # Force both providers to fail so the tool degrades gracefully.
    async def _boom(*args, **kwargs):
        raise RuntimeError("no network")

    monkeypatch.setattr(ws, "_tavily_search", _boom)
    monkeypatch.setattr(ws, "_duckduckgo_search", _boom)
    assert await ws.web_search("anything", 1) == []
