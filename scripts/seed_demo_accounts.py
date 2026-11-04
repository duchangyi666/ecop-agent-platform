"""Provision development identities; this script does not create passwords."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import json
from pathlib import Path
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.auth.config import get_auth_settings
from backend.auth.permissions import ROLE_PERMISSIONS
from backend.config import get_settings
from backend.database.base import TenantScope
from backend.database.models.identity import Permission, Role, Tenant, User
from backend.database.repositories.identity import IdentityRepository
from scripts.seed_demo_identity import ROLE_CODES, seed_demo_identity


@dataclass(frozen=True)
class DemoAccount:
    email: str
    display_name: str
    role_code: str


DEMO_ACCOUNTS = (
    DemoAccount("admin@clouddesk.demo", "演示管理员", "platform_admin"),
    DemoAccount("agent@clouddesk.demo", "演示客服", "support_agent"),
    DemoAccount("finance@clouddesk.demo", "演示财务审核员", "finance_reviewer"),
    DemoAccount("customer@clouddesk.demo", "演示客户", "customer"),
    DemoAccount("guest@clouddesk.demo", "演示访客", "guest"),
)


async def seed_demo_accounts(
    *, database_url: str, tenant_slug: str = "clouddesk-demo"
) -> list[dict[str, str]]:
    if get_auth_settings().auth_mode != "dev":
        raise ValueError("demo accounts can only be provisioned in AUTH_MODE=dev")
    if not tenant_slug.strip() or len(tenant_slug) > 100:
        raise ValueError("tenant_slug must contain 1 to 100 characters")
    tenant_slug = tenant_slug.strip()
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    identities = []
    try:
        async with factory() as session, session.begin():
            tenant = await session.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
            if tenant is None:
                tenant = Tenant(slug=tenant_slug, name="CloudDesk 演示租户", status="active")
                session.add(tenant)
                await session.flush()
            elif tenant.deleted_at is not None or tenant.status != "active":
                raise ValueError("existing demo tenant is inactive or deleted")

            permission_rows = (await session.execute(
                select(Permission, Role).join(Role, Role.id == Permission.role_id).where(
                    Permission.tenant_id == tenant.id,
                )
            )).all()
            for permission, role in permission_rows:
                if (
                    ROLE_CODES.get(permission.code) != role.code
                    or permission.status != "active" or permission.deleted_at is not None
                    or role.status != "active" or role.deleted_at is not None
                ):
                    raise ValueError(
                        "existing tenant has non-demo or disabled permissions; "
                        "use a fresh --tenant-slug"
                    )

            for account in DEMO_ACCOUNTS:
                user = await session.scalar(
                    select(User).where(
                        User.tenant_id == tenant.id, User.email == account.email
                    )
                )
                if user is None:
                    user = User(
                        tenant_id=tenant.id, email=account.email,
                        display_name=account.display_name, status="active",
                    )
                    session.add(user)
                    await session.flush()
                elif user.deleted_at is not None or user.status != "active":
                    raise ValueError(f"existing demo user is inactive or deleted: {account.email}")

                scope = TenantScope(tenant_id=tenant.id, actor_id=user.id, actor_type="user")
                effective = await IdentityRepository(session).list_user_permissions(
                    scope=scope, user_id=user.id
                )
                if set(effective) - ROLE_PERMISSIONS[account.role_code]:
                    raise ValueError(
                        f"existing demo user has extra permissions: {account.email}; "
                        "use a fresh --tenant-slug"
                    )
                identities.append((account, tenant.id, user.id))
    finally:
        await engine.dispose()

    result = []
    for account, tenant_id, user_id in identities:
        # Each permission has one owning role in the current database schema.
        # Reuse the per-permission provisioning roles to express overlapping
        # business-role matrices without moving permissions between users.
        await seed_demo_identity(
            database_url=database_url, tenant_id=tenant_id, user_id=user_id,
            permission_codes=set(ROLE_PERMISSIONS[account.role_code]),
        )
        result.append({
            "tenant_id": str(tenant_id), "tenant_slug": tenant_slug,
            "user_id": str(user_id), "email": account.email,
            "profile": account.role_code,
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=get_settings().database_url)
    parser.add_argument("--tenant-slug", default="clouddesk-demo")
    args = parser.parse_args()
    result = asyncio.run(seed_demo_accounts(
        database_url=args.database_url, tenant_slug=args.tenant_slug
    ))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
