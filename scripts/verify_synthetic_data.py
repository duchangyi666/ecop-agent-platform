"""Verify business consistency of generated synthetic data.

Checks row counts, referential integrity within tenant scope, absence of
cross-tenant references, and that state columns respect their domain values.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.domain.approval import ApprovalStatus
from backend.domain.billing import PaymentStatus, RefundStatus
from backend.domain.ticket import TicketStatus

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _enum_values(enum) -> tuple[str, ...]:
    return tuple(item.value for item in enum)


CHECKS: list[tuple[str, str, list[str]]] = [
    # (label, sql, allowed_values or [] meaning "no value constraint")
    (
        "refund references a payment in the same tenant",
        """
        SELECT count(*) FROM refunds r
        LEFT JOIN payments p ON p.id = r.payment_id AND p.tenant_id = r.tenant_id
        WHERE p.id IS NULL
        """,
        ["0"],
    ),
    (
        "ticket references a customer in the same tenant",
        """
        SELECT count(*) FROM tickets t
        LEFT JOIN customers c ON c.id = t.customer_id AND c.tenant_id = t.tenant_id
        WHERE c.id IS NULL
        """,
        ["0"],
    ),
    (
        "ticket assignee belongs to the same tenant",
        """
        SELECT count(*) FROM tickets t
        LEFT JOIN users u ON u.id = t.current_assignee_id AND u.tenant_id = t.tenant_id
        WHERE t.current_assignee_id IS NOT NULL AND u.id IS NULL
        """,
        ["0"],
    ),
    (
        "approval request links a ticket or refund in the same tenant",
        """
        SELECT count(*) FROM approval_requests a
        LEFT JOIN tickets t ON t.id = a.ticket_id AND t.tenant_id = a.tenant_id
        LEFT JOIN refunds r ON r.id = a.refund_id AND r.tenant_id = a.tenant_id
        WHERE (a.ticket_id IS NOT NULL AND t.id IS NULL)
           OR (a.refund_id IS NOT NULL AND r.id IS NULL)
        """,
        ["0"],
    ),
    (
        "memory record references users/customers in the same tenant",
        """
        SELECT count(*) FROM memory_records m
        LEFT JOIN users u ON u.id = m.user_id AND u.tenant_id = m.tenant_id
        LEFT JOIN customers c ON c.id = m.customer_id AND c.tenant_id = m.tenant_id
        WHERE (m.user_id IS NOT NULL AND u.id IS NULL)
           OR (m.customer_id IS NOT NULL AND c.id IS NULL)
        """,
        ["0"],
    ),
    (
        "no cross-tenant payment/refund links",
        """
        SELECT count(*) FROM refunds r
        JOIN payments p ON p.id = r.payment_id
        WHERE p.tenant_id <> r.tenant_id
        """,
        ["0"],
    ),
    (
        "permission codes are unique per tenant",
        """
        SELECT count(*) FROM (
            SELECT tenant_id, code, count(*) AS n
            FROM permissions GROUP BY tenant_id, code HAVING count(*) > 1
        ) dup
        """,
        ["0"],
    ),
    (
        "user_roles are unique per tenant/user/role",
        """
        SELECT count(*) FROM (
            SELECT tenant_id, user_id, role_id, count(*) AS n
            FROM user_roles GROUP BY tenant_id, user_id, role_id HAVING count(*) > 1
        ) dup
        """,
        ["0"],
    ),
    (
        "refund status is a valid domain value",
        f"SELECT count(*) FROM refunds WHERE status NOT IN {_enum_values(RefundStatus)}",
        ["0"],
    ),
    (
        "payment status is a valid domain value",
        f"SELECT count(*) FROM payments WHERE status NOT IN {_enum_values(PaymentStatus)}",
        ["0"],
    ),
    (
        "ticket status is a valid domain value",
        f"SELECT count(*) FROM tickets WHERE status NOT IN {_enum_values(TicketStatus)}",
        ["0"],
    ),
    (
        "approval status is a valid domain value",
        f"SELECT count(*) FROM approval_requests WHERE status NOT IN {_enum_values(ApprovalStatus)}",
        ["0"],
    ),
]


async def _run_checks(database_url: str) -> tuple[int, int, list[str]]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    results: list[str] = []
    passed = 0
    failed = 0
    try:
        async with engine.connect() as connection:
            for label, sql, expected in CHECKS:
                value = (await connection.execute(text(sql))).scalar()
                ok = str(value) in expected
                if ok:
                    passed += 1
                else:
                    failed += 1
                results.append(f"{'PASS' if ok else 'FAIL'} | {label} | value={value}")
    finally:
        await engine.dispose()
    return passed, failed, results


async def _counts(database_url: str) -> dict[str, int]:
    engine = create_async_engine(database_url, pool_pre_ping=True)
    counts: dict[str, int] = {}
    try:
        async with engine.connect() as connection:
            for table in (
                "tenants",
                "users",
                "roles",
                "permissions",
                "user_roles",
                "customers",
                "customer_contacts",
                "subscriptions",
                "invoices",
                "payments",
                "refunds",
                "tickets",
                "ticket_messages",
                "ticket_events",
                "ticket_assignments",
                "approval_requests",
                "approval_actions",
                "conversations",
                "conversation_messages",
                "policies",
                "policy_versions",
                "documents",
                "document_versions",
                "knowledge_chunks",
                "memory_records",
                "agent_definitions",
                "prompt_definitions",
                "model_profiles",
                "feature_flags",
                "runtime_traces",
                "runtime_spans",
                "tool_executions",
                "workflow_checkpoints",
                "audit_logs",
                "evaluation_datasets",
                "evaluation_cases",
            ):
                value = (
                    await connection.execute(text(f'SELECT count(*) FROM "{table}"'))
                ).scalar()
                counts[table] = int(value)
    finally:
        await engine.dispose()
    return counts


async def main(database_url: str) -> None:
    counts = await _counts(database_url)
    print("row counts:")
    for table, count in counts.items():
        print(f"  {table}: {count}")
    passed, failed, results = await _run_checks(database_url)
    print("consistency checks:")
    for line in results:
        print(f"  {line}")
    print(f"summary: {passed} passed, {failed} failed")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify synthetic data business consistency.")
    parser.add_argument("--database-url", default=os.getenv("DATABASE_URL", get_settings().database_url))
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(main(args.database_url))
