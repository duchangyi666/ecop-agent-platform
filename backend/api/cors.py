from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
ALLOWED_HEADERS = (
    "Authorization",
    "Content-Type",
    "X-Actor-Id",
    "X-Actor-Type",
    "X-Request-Id",
    "X-Tenant-Id",
)


def get_cors_allowed_origins(raw: str | None = None) -> list[str]:
    """Return a validated, de-duplicated CORS origin allowlist.

    The default is empty because same-origin access through the Next.js proxy
    does not require CORS. Wildcards are rejected: this application carries
    tenant and identity credentials and must never reflect arbitrary origins.
    """

    value = os.getenv("CORS_ALLOWED_ORIGINS", "") if raw is None else raw
    origins: list[str] = []
    seen: set[str] = set()
    for item in value.split(","):
        candidate = item.strip().rstrip("/")
        if not candidate:
            continue
        if candidate == "*":
            raise ValueError("CORS_ALLOWED_ORIGINS must not contain a wildcard")
        parsed = urlsplit(candidate)
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(f"invalid CORS origin: {candidate}")
        origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
        if origin not in seen:
            origins.append(origin)
            seen.add(origin)
    return origins


def configure_cors(app: FastAPI) -> None:
    origins = get_cors_allowed_origins()
    if not origins:
        return
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=ALLOWED_METHODS,
        allow_headers=ALLOWED_HEADERS,
        expose_headers=("X-Request-Id",),
        max_age=600,
    )


__all__ = [
    "ALLOWED_HEADERS",
    "ALLOWED_METHODS",
    "configure_cors",
    "get_cors_allowed_origins",
]
