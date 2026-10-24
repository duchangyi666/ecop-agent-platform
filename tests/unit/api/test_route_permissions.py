from __future__ import annotations

from fastapi.routing import APIRoute

from backend.auth.permissions import ALL_PERMISSIONS
from backend.main import create_app

# Routes that are intentionally public or authenticated without a specific
# permission. Keep this list small and review every addition.
_PUBLIC_ROUTES = {
    "/healthz",
    "/readyz",
    "/metrics",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/api/v1/auth/mode",
    "/api/v1/auth/tokens",
    "/api/v1/auth/oidc/config",
    "/api/v1/auth/oidc/exchange",
    "/api/v1/auth/me",
    "/api/v1/identity/tenants",
    "/api/v1/identity/tenants/{tenant_id}/users",
}


def _collect_permission_codes(dependant) -> set[str]:
    codes: set[str] = set()
    for dependency in dependant.dependencies:
        code = getattr(dependency.call, "permission_code", None)
        if code:
            codes.add(code)
        codes.update(_collect_permission_codes(dependency))
    return codes


def _route_matrix() -> dict[tuple[str, str], set[str]]:
    app = create_app()
    matrix: dict[tuple[str, str], set[str]] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        codes = _collect_permission_codes(route.dependant)
        for method in route.methods:
            matrix[(route.path, method)] = codes
    return matrix


def test_route_permissions_are_in_the_canonical_catalog() -> None:
    matrix = _route_matrix()
    known = set(ALL_PERMISSIONS)

    for (path, method), codes in matrix.items():
        if path in _PUBLIC_ROUTES:
            continue
        assert codes, f"{method} {path} is missing require_permission"
        assert codes <= known, f"{method} {path} uses unknown permission: {codes - known}"


def test_sensitive_routes_have_expected_permissions() -> None:
    matrix = _route_matrix()

    assert matrix[("/api/v1/customer-consultations", "POST")] == {"customer.consult"}
    assert matrix[("/api/v1/refunds", "POST")] == {"refund.request"}
    assert matrix[("/api/v1/approvals", "GET")] == {"approval.read"}
    assert matrix[("/api/v1/approvals/{approval_request_id}", "POST")] == {"refund.approve"}
    assert matrix[("/api/v1/knowledge/documents", "POST")] == {"knowledge.ingest"}
    assert matrix[("/api/v1/knowledge/documents/{document_id}", "DELETE")] == {"knowledge.delete"}
    assert matrix[("/api/v1/runtime/traces", "GET")] == {"runtime.read"}
    assert matrix[("/api/v1/evaluations/run", "POST")] == {"evaluation.run"}
