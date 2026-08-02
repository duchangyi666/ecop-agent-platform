from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.database.models.identity import Permission, Role, User, UserRole

SUPPORTED_PERMISSIONS = {
    "refund.request",
    "refund.approve",
    "customer.consult",
    "ticket.create",
    "knowledge.search",
    "knowledge.ingest",
    "evaluation.read",
    "evaluation.run",
}
ROLE_CODES = {
    "refund.request": "demo_refund_requester",
    "refund.approve": "demo_refund_approver",
    "customer.consult": "demo_customer_service_consultant",
    "ticket.create": "demo_ticket_creator",
    "knowledge.search": "demo_knowledge_searcher",
    "knowledge.ingest": "demo_knowledge_ingestor",
    "evaluation.read": "demo_evaluation_reader",
    "evaluation.run": "demo_evaluation_runner",
}


async def seed_demo_identity(
    *,
    database_url: str,
    tenant_id: UUID,
    user_id: UUID,
    permission_codes: set[str] | list[str],
) -> None:
    requested = set(permission_codes)
    unsupported = requested - SUPPORTED_PERMISSIONS
    if unsupported:
        raise ValueError(f"unsupported permission codes: {sorted(unsupported)}")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            user = await session.scalar(
                select(User).where(
                    User.id == user_id,
                    User.tenant_id == tenant_id,
                    User.deleted_at.is_(None),
                    User.status == "active",
                )
            )
            if user is None:
                raise ValueError("active user not found in tenant")

            for permission_code in sorted(requested):
                role = await session.scalar(
                    select(Role).where(
                        Role.tenant_id == tenant_id,
                        Role.code == ROLE_CODES[permission_code],
                        Role.deleted_at.is_(None),
                    )
                )
                if role is None:
                    role = Role(
                        tenant_id=tenant_id,
                        code=ROLE_CODES[permission_code],
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

            await session.commit()
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed development refund permissions for one tenant user.")
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--user-id", type=UUID, required=True)
    parser.add_argument("--permissions", nargs="+", choices=sorted(SUPPORTED_PERMISSIONS), required=True)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    asyncio.run(
        seed_demo_identity(
            database_url=args.database_url,
            tenant_id=args.tenant_id,
            user_id=args.user_id,
            permission_codes=set(args.permissions),
        )
    )
    print("demo identity permissions seeded")


if __name__ == "__main__":
    main()
