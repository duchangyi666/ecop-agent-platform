from __future__ import annotations

import asyncio
import os
from urllib.parse import urlparse

from sqlalchemy import text

from backend.database.session import get_session_factory


async def _database() -> str:
    async with get_session_factory()() as session:
        await session.execute(text("select 1"))
    return "ok"


async def _redis() -> str:
    url = os.getenv("REDIS_URL", "").strip()
    if not url:
        return "skipped"
    import redis.asyncio as redis

    client = redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
    try:
        await client.ping()
        return "ok"
    finally:
        await client.aclose()


async def _milvus() -> str:
    uri = os.getenv("MILVUS_URI", "").strip()
    if not uri:
        return "skipped"
    parsed = urlparse(uri if "://" in uri else f"http://{uri}")
    host = parsed.hostname or "localhost"
    port = parsed.port or 19530
    reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout=2)
    writer.close()
    await writer.wait_closed()
    return "ok"


async def readiness_report() -> tuple[bool, dict[str, str]]:
    components: dict[str, str] = {}
    try:
        components["database"] = await _database()
    except Exception:  # noqa: BLE001 - report degraded, never leak details
        components["database"] = "unavailable"
    for name, check in (("redis", _redis), ("milvus", _milvus)):
        try:
            components[name] = await check()
        except Exception:  # noqa: BLE001
            components[name] = "unavailable"
    # Database is required; Redis/Milvus are reported for operators and may be
    # disabled locally without failing readiness.
    ready = components["database"] == "ok"
    return ready, components


__all__ = ["readiness_report"]
