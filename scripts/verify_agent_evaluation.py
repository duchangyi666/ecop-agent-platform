from __future__ import annotations

"""Verify the agent evaluation pipeline.

Part 1 (offline, no database): checks that the seeded guard cases actually hit
the security rules as labelled - a guard dataset that does not fire is a
useless dataset, so this is validated before any DB evaluation runs.

Part 2 (requires PostgreSQL + optionally a model key): seeds the datasets and
runs the guard + correctness evaluations through the real runner.

Usage:
    python scripts/verify_agent_evaluation.py --tenant-id <uuid> [--database-url ...]
    python scripts/verify_agent_evaluation.py --offline-only   # part 1 only
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.agent.guards import DomainGuard, InputSecurityGuard  # noqa: E402
from backend.config import get_settings  # noqa: E402
from scripts.seed_agent_evaluation import GUARD_CASES  # noqa: E402


def verify_guard_dataset_offline() -> dict[str, object]:
    """Run every seeded guard case against the real guards and report hits."""
    input_guard = InputSecurityGuard()
    domain_guard = DomainGuard()
    blocked = {"block", "human_handoff"}
    stats = {"total": 0, "status_hit": 0, "domain_hit": 0, "domain_count": 0,
             "blocked_hit": 0, "failures": []}
    for message, expected_status, expected_domain in GUARD_CASES:
        stats["total"] += 1
        decision = input_guard.evaluate(message)
        status_hit = decision.status == expected_status
        domain_hit = True
        if expected_status == "allow" and expected_domain:
            stats["domain_count"] += 1
            domain_decision = domain_guard.evaluate(message)
            domain_hit = (
                domain_decision.status == "in_scope"
                and domain_decision.domain == expected_domain
            )
        expected_blocked = expected_status in blocked
        actual_blocked = decision.status in blocked
        blocked_hit = expected_blocked == actual_blocked
        if status_hit:
            stats["status_hit"] += 1
        if expected_status == "allow" and expected_domain and domain_hit:
            stats["domain_hit"] += 1
        if blocked_hit:
            stats["blocked_hit"] += 1
        if not (status_hit and domain_hit):
            stats["failures"].append(
                {
                    "case": message[:40],
                    "expected_status": expected_status,
                    "actual_status": decision.status,
                    "domain_hit": domain_hit,
                }
            )
    stats["status_accuracy"] = stats["status_hit"] / stats["total"]
    stats["domain_accuracy"] = (
        stats["domain_hit"] / stats["domain_count"] if stats["domain_count"] else None
    )
    stats["blocked_accuracy"] = stats["blocked_hit"] / stats["total"]
    return stats


async def run_db_evaluations(
    *,
    database_url: str,
    tenant_id: UUID,
    qa_limit: int = 3,
    guard_limit: int = 20,
) -> None:
    from backend.database.base import TenantScope
    from backend.database.unit_of_work import UnitOfWork
    from backend.evaluation.agent_runner import AgentEvaluationRunner
    from backend.llm.factory import create_model_gateway
    from backend.rag.config import get_rag_settings
    from backend.rag.reranker import create_reranker
    from backend.rag.retriever import ConsultationKnowledgeRetriever
    from backend.rag.vector_store import create_knowledge_vector_store
    from scripts.seed_agent_evaluation import seed_agent_evaluation

    created = await seed_agent_evaluation(
        database_url=database_url,
        tenant_id=tenant_id,
    )
    print(f"[seed] created: {created}")

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(database_url, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    scope = TenantScope(tenant_id=tenant_id)
    gateway = create_model_gateway()
    retriever = ConsultationKnowledgeRetriever(
        session_factory,
        vector_store=create_knowledge_vector_store(),
        reranker=create_reranker(get_rag_settings()),
    )
    runner = AgentEvaluationRunner(
        session_factory,
        retriever=retriever,
        model_gateway=gateway,
    )
    try:
        guard_result = await runner.run_guard_evaluation(
            scope=scope,
            dataset_code="agent-guard",
            limit=guard_limit,
        )
        print(f"[guard] {guard_result.metrics}")

        correctness_result = await runner.run_correctness_evaluation(
            scope=scope,
            dataset_code="agent-qa",
            limit=qa_limit,
        )
        print(f"[correctness] {correctness_result.metrics}")
    finally:
        await engine.dispose()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the agent evaluation pipeline.")
    parser.add_argument("--offline-only", action="store_true", help="only check guard dataset quality offline")
    parser.add_argument("--tenant-id", type=UUID, default=None)
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    parser.add_argument("--qa-limit", type=int, default=3)
    parser.add_argument("--guard-limit", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    stats = verify_guard_dataset_offline()
    print(f"[offline guard dataset check] {stats}")
    if args.offline_only:
        return
    if args.tenant_id is None:
        print("[skip db] --tenant-id is required for db evaluations; use --offline-only to skip")
        return
    asyncio.run(
        run_db_evaluations(
            database_url=args.database_url,
            tenant_id=args.tenant_id,
            qa_limit=args.qa_limit,
            guard_limit=args.guard_limit,
        )
    )


if __name__ == "__main__":
    main()
