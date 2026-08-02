from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.config import get_settings
from backend.database.base import TenantScope
from backend.database.session import get_session_factory
from backend.database.unit_of_work import UnitOfWork
from backend.llm.gateway import ModelGateway


@dataclass(frozen=True, slots=True)
class RequestContext:
    scope: TenantScope
    request_id: str


def _invalid_context(message: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"code": "invalid_tenant_context", "message": message},
    )


def _parse_uuid(value: str | None, field_name: str) -> UUID:
    if not value:
        raise _invalid_context(f"{field_name} is required")
    try:
        return UUID(value)
    except (TypeError, ValueError) as exc:
        raise _invalid_context(f"{field_name} must be a UUID") from exc


def get_request_context(
    x_tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    x_actor_id: Annotated[str | None, Header(alias="X-Actor-Id")] = None,
    x_actor_type: Annotated[str | None, Header(alias="X-Actor-Type")] = None,
    x_request_id: Annotated[str | None, Header(alias="X-Request-Id")] = None,
) -> RequestContext:
    if not x_actor_type or not x_actor_type.strip():
        raise _invalid_context("X-Actor-Type is required")
    return RequestContext(
        scope=TenantScope(
            tenant_id=_parse_uuid(x_tenant_id, "X-Tenant-Id"),
            actor_id=_parse_uuid(x_actor_id, "X-Actor-Id"),
            actor_type=x_actor_type.strip(),
        ),
        request_id=x_request_id or f"request-{uuid4().hex}",
    )


def get_database_url() -> str:
    return get_settings().database_url


def get_session_factory_dependency() -> async_sessionmaker[AsyncSession]:
    return get_session_factory()


def get_app_model_gateway(request: Request) -> ModelGateway:
    return request.app.state.model_gateway


def require_permission(permission_code: str):
    async def dependency(
        context=Depends(get_request_context),
        session_factory=Depends(get_session_factory_dependency),
    ) -> RequestContext:
        async with UnitOfWork(session_factory, scope=context.scope) as uow:
            actor_id = context.scope.actor_id
            if actor_id is None:
                raise HTTPException(
                    status_code=403,
                    detail={"code": "tenant_identity_invalid", "message": "tenant identity is invalid"},
                )
            user = await uow.identity.get_user_in_tenant(scope=context.scope, user_id=actor_id)
            if user is None or user.status != "active":
                raise HTTPException(
                    status_code=403,
                    detail={"code": "tenant_identity_invalid", "message": "tenant identity is invalid"},
                )
            if not await uow.identity.has_permission(
                scope=context.scope,
                user_id=actor_id,
                permission_code=permission_code,
            ):
                raise HTTPException(
                    status_code=403,
                    detail={"code": "permission_denied", "message": "permission denied"},
                )
        return context

    return dependency


__all__ = [
    "RequestContext",
    "get_app_model_gateway",
    "get_database_url",
    "get_request_context",
    "get_session_factory_dependency",
    "require_permission",
]
