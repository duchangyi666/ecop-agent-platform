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
from backend.database.base import TenantScope
from backend.database.models.governance import Document, EvaluationCase
from backend.database.repositories.evaluation import EvaluationRepository


async def seed_evaluation_dataset(
    *,
    database_url: str,
    tenant_id: UUID,
    dataset_code: str,
    name: str,
) -> int:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    scope = TenantScope(tenant_id=tenant_id)
    created = 0
    try:
        async with session_factory() as session:
            repository = EvaluationRepository(session)
            dataset = await repository.get_dataset_by_code(
                scope=scope,
                dataset_code=dataset_code,
            )
            if dataset is None:
                dataset = await repository.create_dataset(
                    scope=scope,
                    dataset_code=dataset_code,
                    name=name,
                )
            documents = list(
                await session.scalars(
                    select(Document).where(
                        Document.tenant_id == tenant_id,
                        Document.status == "active",
                        Document.deleted_at.is_(None),
                    )
                )
            )
            for document in documents:
                case_key = f"doc-{document.id}"
                existing = await session.scalar(
                    select(EvaluationCase).where(
                        EvaluationCase.tenant_id == tenant_id,
                        EvaluationCase.dataset_id == dataset.id,
                        EvaluationCase.case_key == case_key,
                        EvaluationCase.deleted_at.is_(None),
                    )
                )
                if existing is not None:
                    continue
                await repository.create_case(
                    scope=scope,
                    dataset_id=dataset.id,
                    case_key=case_key,
                    input_summary=document.title,
                    expected_summary={"document_ids": [str(document.id)]},
                    tags=["retrieval", "synthetic"],
                )
                created += 1
            await session.commit()
    finally:
        await engine.dispose()
    return created


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a tenant retrieval evaluation dataset.")
    parser.add_argument("--tenant-id", type=UUID, required=True)
    parser.add_argument("--dataset-code", required=True)
    parser.add_argument("--name", default="Tenant Retrieval Dataset")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    created = asyncio.run(
        seed_evaluation_dataset(
            database_url=args.database_url,
            tenant_id=args.tenant_id,
            dataset_code=args.dataset_code,
            name=args.name,
        )
    )
    print(f"evaluation dataset seeded: {created} cases")


if __name__ == "__main__":
    main()
