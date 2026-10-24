from __future__ import annotations

from collections.abc import Mapping

from starlette.responses import Response


CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
        "object-src 'none'",
        "img-src 'self' data: https://fastapi.tiangolo.com",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net",
    )
)

SECURITY_HEADERS: Mapping[str, str] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}

HSTS_HEADER = "max-age=31536000; includeSubDomains"


def apply_security_headers(response: Response, *, is_https: bool) -> None:
    """Attach browser security headers without overriding route-specific values.

    HSTS is emitted only for HTTPS requests so local HTTP development cannot
    accidentally pin a browser to an unavailable TLS endpoint.
    """

    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    if is_https:
        response.headers.setdefault("Strict-Transport-Security", HSTS_HEADER)


__all__ = [
    "CONTENT_SECURITY_POLICY",
    "HSTS_HEADER",
    "SECURITY_HEADERS",
    "apply_security_headers",
]
