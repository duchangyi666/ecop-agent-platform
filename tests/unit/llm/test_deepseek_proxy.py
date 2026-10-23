from __future__ import annotations

import os

import pytest

from backend.llm.deepseek import _build_async_client


@pytest.mark.asyncio
async def test_bracketed_no_proxy_is_sanitized(monkeypatch) -> None:
    monkeypatch.setenv("NO_PROXY", "localhost,127.0.0.1,::1,[::1]")
    monkeypatch.setenv("no_proxy", "localhost,127.0.0.1,::1,[::1]")

    client = _build_async_client()
    try:
        assert "[" not in os.environ["NO_PROXY"]
        assert "::1" in os.environ["NO_PROXY"]
        assert os.environ["NO_PROXY"].count("::1") == 1
    finally:
        await client.aclose()
