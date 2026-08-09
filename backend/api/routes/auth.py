from __future__ import annotations

import os
import re
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.auth.config import get_auth_settings
from backend.auth.passwords import hash_password, verify_password
from backend.auth.tokens import create_access_token
from backend.database.base import TenantScope, utc_now
from backend.database.models.identity import Permission, Role, Tenant, User, UserRole
from backend.database.unit_of_work import UnitOfWork
from backend.api.dependencies import get_session_factory_dependency

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# Permissions granted to every self-registered account. Admin roles can be
# assigned later through the identity pipeline.
DEFAULT_REGISTER_PERMISSIONS = (
    "customer.consult",
    "conversation.create",
    "conversation.read",
    "conversation.write",
    "ticket.create",
    "ticket.read",
    "knowledge.search",
)
_ROLE_CODES = {
    "customer.consult": "demo_customer_service_consultant",
    "conversation.create": "demo_conversation_creator",
    "conversation.read": "demo_conversation_reader",
    "conversation.write": "demo_conversation_writer",
    "ticket.create": "demo_ticket_creator",
    "ticket.read": "demo_ticket_reader",
    "knowledge.search": "demo_knowledge_searcher",
}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")


def _is_jwt_only() -> bool:
    return os.getenv("AUTH_MODE", "dev").strip().lower() == "jwt-only"


def _require_auth_configured() -> None:
    settings = get_auth_settings()
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_not_configured",
                "message": "JWT_SECRET is not configured",
            },
        )


async def _ensure_role_permission_assignment(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    user_id: UUID,
    permission_code: str,
) -> None:
    """Idempotently create role + permission + user-role assignment for a code."""
    role_code = _ROLE_CODES[permission_code]
    role = await session.scalar(
        select(Role).where(
            Role.tenant_id == tenant_id,
            Role.code == role_code,
            Role.deleted_at.is_(None),
        )
    )
    if role is None:
        role = Role(
            tenant_id=tenant_id,
            code=role_code,
            name=permission_code,
            status="active",
            is_platform_role=False,
        )
        session.add(role)
        await session.flush()
    elif role.status != "active":
        role.status = "active"

    permission = await session.scalar(
        select(Permission).where(
            Permission.tenant_id == tenant_id,
            Permission.code == permission_code,
            Permission.deleted_at.is_(None),
        )
    )
    if permission is None:
        permission = Permission(
            tenant_id=tenant_id,
            role_id=role.id,
            code=permission_code,
            name=permission_code,
            status="active",
        )
        session.add(permission)
    else:
        permission.role_id = role.id
        permission.status = "active"

    assignment = await session.scalar(
        select(UserRole).where(
            UserRole.tenant_id == tenant_id,
            UserRole.user_id == user_id,
            UserRole.role_id == role.id,
            UserRole.deleted_at.is_(None),
        )
    )
    if assignment is None:
        session.add(UserRole(tenant_id=tenant_id, user_id=user_id, role_id=role.id))


async def _ensure_tenant(session: AsyncSession, *, slug: str, name: str) -> Tenant:
    tenant = await session.scalar(
        select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
    )
    if tenant is not None:
        return tenant
    tenant = Tenant(slug=slug, name=name, status="active")
    session.add(tenant)
    await session.flush()
    return tenant


class AuthTokenRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    tenant_id: UUID
    user_id: UUID
    actor_type: Literal["user", "system"] = "user"


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(ge=1)


@router.post("/tokens", response_model=AuthTokenResponse)
async def issue_local_access_token(
    payload: AuthTokenRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> AuthTokenResponse:
    # Self-service token issuance is a local-development convenience only.
    # In production (AUTH_MODE=jwt-only) real identity providers issue tokens.
    if _is_jwt_only():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "not_found", "message": "not found"},
        )
    settings = get_auth_settings()
    if not settings.jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "auth_not_configured",
                "message": "JWT_SECRET is not configured",
            },
        )

    scope = TenantScope(
        tenant_id=payload.tenant_id,
        actor_id=payload.user_id,
        actor_type=payload.actor_type,
    )
    async with UnitOfWork(session_factory, scope=scope) as uow:
        user = await uow.identity.get_user_in_tenant(
            scope=scope,
            user_id=payload.user_id,
        )
        if user is None or user.status != "active":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "tenant_identity_invalid",
                    "message": "tenant identity is invalid",
                },
            )

    token = create_access_token(
        tenant_id=payload.tenant_id,
        user_id=payload.user_id,
        actor_type=payload.actor_type,
        secret=settings.jwt_secret,
        expires_minutes=settings.token_expires_minutes,
    )
    return AuthTokenResponse(
        access_token=token,
        expires_in=settings.token_expires_minutes * 60,
    )


class RegisterRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=128)
    tenant_slug: str | None = Field(default=None, min_length=2, max_length=63)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        if not _EMAIL_RE.fullmatch(value):
            raise ValueError("invalid email address")
        return value.lower()

    @field_validator("tenant_slug")
    @classmethod
    def _validate_tenant_slug(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SLUG_RE.fullmatch(value):
            raise ValueError("tenant slug must be lowercase letters, digits and hyphens")
        return value


class LoginRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=128)
    tenant_slug: str | None = Field(default=None, min_length=2, max_length=63)


class AuthSessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(ge=1)
    tenant_id: UUID
    tenant_slug: str
    user_id: UUID
    display_name: str
    email: str
    actor_type: Literal["user", "system"] = "user"


@router.post("/register", response_model=AuthSessionResponse)
async def register_account(
    payload: RegisterRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> AuthSessionResponse:
    """Create a tenant (if needed) + account and return a signed JWT session."""
    _require_auth_configured()
    settings = get_auth_settings()
    if payload.tenant_slug:
        # Explicit tenant slug: reuse the existing tenant (if any) and check
        # email uniqueness inside it, instead of auto-creating a suffixed copy.
        slug = payload.tenant_slug
    else:
        slug = await _unique_slug(session_factory, _slug_from_email(payload.email))

    async with session_factory() as session:
        tenant = await _ensure_tenant(session, slug=slug, name=f"{slug} 组织")
        existing = await session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == payload.email,
                User.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "email_registered", "message": "该邮箱已在当前租户注册"},
            )
        user = User(
            tenant_id=tenant.id,
            email=payload.email,
            display_name=payload.display_name,
            password_hash=hash_password(payload.password),
            status="active",
        )
        session.add(user)
        await session.flush()
        for permission_code in DEFAULT_REGISTER_PERMISSIONS:
            await _ensure_role_permission_assignment(
                session,
                tenant_id=tenant.id,
                user_id=user.id,
                permission_code=permission_code,
            )
        await session.commit()
        tenant_slug = tenant.slug

    token = create_access_token(
        tenant_id=user.tenant_id,
        user_id=user.id,
        actor_type="user",
        secret=settings.jwt_secret,
        expires_minutes=settings.token_expires_minutes,
    )
    return _session_response(token=token, tenant_slug=tenant_slug, user=user, settings=settings)


@router.post("/login", response_model=AuthSessionResponse)
async def login_account(
    payload: LoginRequest,
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_session_factory_dependency),
) -> AuthSessionResponse:
    """Verify credentials and return a signed JWT session."""
    _require_auth_configured()
    settings = get_auth_settings()
    email = payload.email.strip().lower()

    statement = select(User).where(
        User.email == email,
        User.status == "active",
        User.deleted_at.is_(None),
        User.password_hash.is_not(None),
    )
    if payload.tenant_slug:
        tenant = await _find_tenant(session_factory, payload.tenant_slug)
        if tenant is None:
            raise _invalid_credentials()
        statement = statement.where(User.tenant_id == tenant.id)

    async with session_factory() as session:
        users = list((await session.scalars(statement)).all())
        matched = None
        for candidate in users:
            if verify_password(payload.password, candidate.password_hash or ""):
                matched = candidate
                break
        if matched is None:
            raise _invalid_credentials()
        tenant = await session.get(Tenant, matched.tenant_id)
        if tenant is None or tenant.status != "active":
            raise _invalid_credentials()
        matched.last_login_at = utc_now()
        await session.commit()

    token = create_access_token(
        tenant_id=matched.tenant_id,
        user_id=matched.id,
        actor_type="user",
        secret=settings.jwt_secret,
        expires_minutes=settings.token_expires_minutes,
    )
    return _session_response(token=token, tenant_slug=tenant.slug, user=matched, settings=settings)


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_credentials", "message": "邮箱或密码错误"},
    )


def _slug_from_email(email: str) -> str:
    prefix = email.split("@")[0].lower()
    prefix = re.sub(r"[^a-z0-9-]", "-", prefix).strip("-")
    return prefix[:40] or "user"


async def _unique_slug(session_factory, slug: str) -> str:
    tenant = await _find_tenant(session_factory, slug)
    if tenant is None:
        return slug
    for suffix in range(1, 100):
        candidate = f"{slug}-{suffix}"
        if await _find_tenant(session_factory, candidate) is None:
            return candidate
    return f"{slug}-{uuid4().hex[:8]}"


async def _find_tenant(session_factory, slug: str) -> Tenant | None:
    async with session_factory() as session:
        return await session.scalar(
            select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
        )


def _session_response(*, token: str, tenant_slug: str, user: User, settings) -> AuthSessionResponse:
    return AuthSessionResponse(
        access_token=token,
        expires_in=settings.token_expires_minutes * 60,
        tenant_id=user.tenant_id,
        tenant_slug=tenant_slug,
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        actor_type="user",
    )


__all__ = [
    "AuthTokenRequest",
    "AuthTokenResponse",
    "RegisterRequest",
    "LoginRequest",
    "AuthSessionResponse",
    "router",
]
