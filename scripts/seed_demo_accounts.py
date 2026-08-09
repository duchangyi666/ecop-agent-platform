"""Seed 5 demo accounts (tenant + user + password + default permissions).

Idempotent: re-running updates passwords/permissions to match this file.

Usage:
    python scripts/seed_demo_accounts.py
    # or with an explicit database URL:
    python scripts/seed_demo_accounts.py --database-url postgresql+asyncpg://app:app@localhost:54329/enterprise_customer_operations
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.passwords import hash_password
from backend.config import get_settings
from backend.database.models.identity import Permission, Role, Tenant, User, UserRole

# email -> (password, display_name, tenant_slug, permissions)
DEMO_ACCOUNTS: list[dict] = [
    {
        "email": "admin@clouddesk.demo",
        "password": "Admin@123456",
        "display_name": "平台管理员",
        "tenant_slug": "demo-ops",
        "permissions": [
            "refund.request", "refund.approve", "customer.consult",
            "conversation.create", "conversation.read", "conversation.write",
            "ticket.create", "ticket.read", "ticket.update",
            "approval.read", "knowledge.search", "knowledge.ingest",
            "knowledge.delete", "evaluation.read", "evaluation.run",
            "runtime.read",
        ],
    },
    {
        "email": "agent@clouddesk.demo",
        "password": "Agent@123456",
        "display_name": "客服专员",
        "tenant_slug": "demo-ops",
        "permissions": [
            "customer.consult",
            "conversation.create", "conversation.read", "conversation.write",
            "ticket.create", "ticket.read", "ticket.update",
            "knowledge.search", "knowledge.ingest", "runtime.read",
        ],
    },
    {
        "email": "finance@clouddesk.demo",
        "password": "Finance@123456",
        "display_name": "财务审核员",
        "tenant_slug": "demo-ops",
        "permissions": [
            "refund.request", "refund.approve", "approval.read",
            "customer.consult", "ticket.read", "conversation.read",
            "knowledge.search", "runtime.read",
        ],
    },
    {
        "email": "customer@clouddesk.demo",
        "password": "Customer@123456",
        "display_name": "演示客户",
        "tenant_slug": "demo-ops",
        "permissions": [
            "customer.consult",
            "conversation.create", "conversation.read", "conversation.write",
            "ticket.create", "ticket.read", "knowledge.search",
        ],
    },
    {
        "email": "guest@clouddesk.demo",
        "password": "Guest@123456",
        "display_name": "访客",
        "tenant_slug": "demo-ops",
        "permissions": [
            "conversation.read", "knowledge.search", "ticket.read",
        ],
    },
]

_ROLE_CODES = {
    "approval.read": "demo_approval_reader",
    "conversation.create": "demo_conversation_creator",
    "conversation.read": "demo_conversation_reader",
    "conversation.write": "demo_conversation_writer",
    "refund.request": "demo_refund_requester",
    "refund.approve": "demo_refund_approver",
    "customer.consult": "demo_customer_service_consultant",
    "ticket.create": "demo_ticket_creator",
    "ticket.read": "demo_ticket_reader",
    "ticket.update": "demo_ticket_updater",
    "knowledge.search": "demo_knowledge_searcher",
    "knowledge.ingest": "demo_knowledge_ingestor",
    "knowledge.delete": "demo_knowledge_deleter",
    "evaluation.read": "demo_evaluation_reader",
    "evaluation.run": "demo_evaluation_runner",
    "runtime.read": "demo_runtime_reader",
}


async def _ensure_tenant(session, slug: str) -> Tenant:
    tenant = await session.scalar(
        select(Tenant).where(Tenant.slug == slug, Tenant.deleted_at.is_(None))
    )
    if tenant is None:
        tenant = Tenant(slug=slug, name=f"{slug} 组织", status="active")
        session.add(tenant)
        await session.flush()
    return tenant


async def _ensure_user(session, tenant_id, email, password, display_name) -> User:
    user = await session.scalar(
        select(User).where(
            User.tenant_id == tenant_id,
            User.email == email,
            User.deleted_at.is_(None),
        )
    )
    if user is None:
        user = User(
            tenant_id=tenant_id,
            email=email,
            display_name=display_name,
            password_hash=hash_password(password),
            status="active",
        )
        session.add(user)
        await session.flush()
    else:
        user.password_hash = hash_password(password)
        user.display_name = display_name
        user.status = "active"
    return user


async def _grant_permission(session, *, tenant_id, user_id, permission_code) -> None:
    role = await session.scalar(
        select(Role).where(
            Role.tenant_id == tenant_id,
            Role.code == _ROLE_CODES[permission_code],
            Role.deleted_at.is_(None),
        )
    )
    if role is None:
        role = Role(
            tenant_id=tenant_id,
            code=_ROLE_CODES[permission_code],
            name=permission_code,
            status="active",
            is_platform_role=False,
        )
        session.add(role)
        await session.flush()
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


async def seed_demo_accounts(database_url: str) -> None:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            for account in DEMO_ACCOUNTS:
                tenant = await _ensure_tenant(session, account["tenant_slug"])
                user = await _ensure_user(
                    session,
                    tenant.id,
                    account["email"],
                    account["password"],
                    account["display_name"],
                )
                for permission_code in account["permissions"]:
                    await _grant_permission(
                        session,
                        tenant_id=tenant.id,
                        user_id=user.id,
                        permission_code=permission_code,
                    )
                print(
                    f"seeded {account['email']:28s} tenant={account['tenant_slug']:10s} "
                    f"permissions={len(account['permissions'])}"
                )
            await session.commit()
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed 5 CloudDesk demo accounts.")
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL", get_settings().database_url),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(seed_demo_accounts(args.database_url))
    print("\ndemo accounts ready. See scripts/seed_demo_accounts.py for credentials.")


if __name__ == "__main__":
    main()
