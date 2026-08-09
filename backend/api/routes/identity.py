from __future__ import annotations

import os
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.api.dependencies import get_session_factory_dependency
from backend.api.schemas import (
    IdentityUserItem,
    TenantItem,
    TenantListResponse,
    TenantUsersResponse,
)
from backend.database.models.identity import Role, Tenant, User, UserRole

router = APIRouter(prefix="/api/v1/identity", tags=["identity"])


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id") or f"request-{uuid4().hex}"


def _reject_in_production() -> None:
    # The identity directory is a development bootstrap aid. In production
    # (AUTH_MODE=jwt-only) it must not be reachable by unauthenticated callers.
    if os.getenv("AUTH_MODE", "dev").strip().lower() == "jwt-only":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "not found"},
        )


@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    request: Request,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    limit: int = Query(default=200, ge=1, le=500),
) -> TenantListResponse:
    _reject_in_production()
    async with session_factory() as session:
        tenants = list(
            (
                await session.scalars(
                    select(Tenant)
                    .where(Tenant.deleted_at.is_(None))
                    .order_by(Tenant.created_at)
                    .limit(limit)
                )
            ).all()
        )
    return TenantListResponse(
        request_id=_request_id(request),
        tenants=[
            TenantItem(id=tenant.id, slug=tenant.slug, name=tenant.name, status=tenant.status)
            for tenant in tenants
        ],
    )


@router.get("/tenants/{tenant_id}/users", response_model=TenantUsersResponse)
async def list_tenant_users(
    tenant_id: UUID,
    request: Request,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
    limit: int = Query(default=500, ge=1, le=1000),
) -> TenantUsersResponse:
    _reject_in_production()
    async with session_factory() as session:
        tenant = await session.scalar(
            select(Tenant).where(
                Tenant.id == tenant_id,
                Tenant.deleted_at.is_(None),
            )
        )
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "tenant_not_found", "message": "tenant not found"},
            )
        users = list(
            (
                await session.scalars(
                    select(User)
                    .where(
                        User.tenant_id == tenant_id,
                        User.deleted_at.is_(None),
                    )
                    .order_by(User.created_at)
                    .limit(limit)
                )
            ).all()
        )
        user_ids = [user.id for user in users]
        role_rows = (
            await session.execute(
                select(UserRole.user_id, Role.code)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    UserRole.tenant_id == tenant_id,
                    UserRole.user_id.in_(user_ids),
                    UserRole.deleted_at.is_(None),
                    Role.deleted_at.is_(None),
                )
            )
        ).all()
    roles_by_user: dict[UUID, list[str]] = {}
    for user_id, role_code in role_rows:
        roles_by_user.setdefault(user_id, []).append(role_code)
    return TenantUsersResponse(
        request_id=_request_id(request),
        tenant_id=tenant_id,
        users=[
            IdentityUserItem(
                id=user.id,
                email=user.email,
                display_name=user.display_name,
                status=user.status,
                roles=sorted(roles_by_user.get(user.id, [])),
            )
            for user in users
        ],
    )


__all__ = ["router"]
