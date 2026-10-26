"""Seed a small development scenario with identities and business data together."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.database.base import TenantScope
from backend.database.models.governance import Document, DocumentVersion
from backend.database.models.identity import Tenant, User
from backend.database.tenant_context import set_tenant_context
from backend.rag.ingestion import KnowledgeIngestRequest, KnowledgeIngestService
from scripts.seed_demo_accounts import seed_demo_accounts
from scripts.seed_demo_minimal import (
    KNOWLEDGE_DOCS, _ensure_customer, _ensure_payment, _ensure_ticket,
)


async def seed_demo_scenario(
    *, database_url: str, tenant_slug: str = "clouddesk-demo"
) -> dict[str, object]:
    identities = await seed_demo_accounts(database_url=database_url, tenant_slug=tenant_slug)
    by_profile = {item["profile"]: item for item in identities}
    tenant_id = UUID(identities[0]["tenant_id"])
    admin_id = UUID(by_profile["platform_admin"]["user_id"])
    scope = TenantScope(tenant_id=tenant_id, actor_id=admin_id, actor_type="user")
    engine = create_async_engine(database_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session, session.begin():
            await set_tenant_context(session, tenant_id)
            tenant = await session.get(Tenant, tenant_id)
            customer_user = await session.get(User, UUID(by_profile["customer"]["user_id"]))
            agent = await session.get(User, UUID(by_profile["support_agent"]["user_id"]))
            customer = await _ensure_customer(session, tenant, customer_user)
            ticket = await _ensure_ticket(session, tenant, customer, agent)
            payment = await _ensure_payment(
                session, tenant, customer,
                external_payment_id="demo-scenario-payment-1280",
                amount=Decimal("1280.00"),
                paid_at=datetime.now(timezone.utc) - timedelta(hours=2),
            )
            customer_id, ticket_id, payment_id = customer.id, ticket.id, payment.id

        # Keep this baseline fully offline: PostgreSQL stores the documents
        # and chunks; vector indexing remains a separate optional operation.
        service = KnowledgeIngestService(factory, vector_store=None)
        document_ids = []
        for doc in KNOWLEDGE_DOCS:
            content_hash = hashlib.sha256(doc["content"].encode("utf-8")).hexdigest()
            async with factory() as session, session.begin():
                await set_tenant_context(session, tenant_id)
                existing = (await session.execute(
                    select(Document, DocumentVersion)
                    .join(DocumentVersion, DocumentVersion.document_id == Document.id)
                    .where(
                        Document.tenant_id == tenant_id,
                        Document.external_document_id == doc["external_document_id"],
                        Document.deleted_at.is_(None),
                        Document.status == "active",
                        DocumentVersion.tenant_id == tenant_id,
                        DocumentVersion.deleted_at.is_(None),
                    )
                    .order_by(DocumentVersion.version_number.desc()).limit(1)
                )).first()
                if (
                    existing is not None and existing[1].content_hash == content_hash
                    and existing[0].title == doc["title"]
                    and existing[0].visibility == "tenant"
                ):
                    document_ids.append(str(existing[0].id))
                    continue

            result = await service.run(scope=scope, request=KnowledgeIngestRequest(
                thread_id=f"demo-seed-{uuid4().hex}",
                external_document_id=doc["external_document_id"],
                title=doc["title"], content=doc["content"], visibility="tenant",
                source_uri=f"demo://knowledge/{doc['external_document_id']}",
            ))
            document_ids.append(str(result.document_id))

        return {
            "tenant_id": str(tenant_id), "identities": identities,
            "customer_id": str(customer_id), "ticket_id": str(ticket_id),
            "payment_id": str(payment_id), "document_ids": document_ids,
            "knowledge_storage": "postgresql", "payment_execution": "local-only",
        }
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", default=get_settings().database_url)
    parser.add_argument("--tenant-slug", default="clouddesk-demo")
    args = parser.parse_args()
    result = asyncio.run(seed_demo_scenario(
        database_url=args.database_url, tenant_slug=args.tenant_slug,
    ))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
