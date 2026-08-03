"""Business-consistent synthetic data generation.

Generates a full CloudDesk tenant graph respecting foreign keys, unique
constraints and domain state machines. Data is written per-tenant in
dependency order with batched commits so the full profile remains feasible.
"""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database.base import Base, utc_now
from backend.database.models.billing import (
    Customer,
    CustomerContact,
    Invoice,
    Payment,
    Refund,
    Subscription,
)
from backend.database.models.governance import (
    AgentDefinition,
    AgentVersion,
    Document,
    DocumentVersion,
    EvaluationCase,
    EvaluationDataset,
    FeatureFlag,
    MemoryRecord,
    ModelProfile,
    Policy,
    PolicyVersion,
    PromptDefinition,
    PromptVersion,
    RuntimeSpan,
    RuntimeTrace,
    ToolExecution,
    WorkflowCheckpoint,
)
from backend.database.models.identity import Permission, Role, Tenant, User, UserRole
from backend.database.models.knowledge import KnowledgeChunk
from backend.database.models.support import (
    ApprovalAction,
    ApprovalRequest,
    AuditLog,
    Conversation,
    ConversationMessage,
    Ticket,
    TicketAssignment,
    TicketEvent,
    TicketMessage,
)
from backend.domain.common import InvalidStateTransition
from backend.domain.ticket import transition_ticket

from scripts.synthetic_data.config import (
    CONVERSATION_CHANNELS,
    CONVERSATION_STATUSES,
    CURRENCY,
    CUSTOMER_STATUSES,
    DOCUMENT_SOURCES,
    DOCUMENT_VISIBILITIES,
    EVALUATION_DATASETS,
    EVALUATION_DATASET_WEIGHTS,
    FEATURE_FLAGS,
    INVOICE_STATUSES,
    MEMORY_TYPES,
    PAYMENT_STATUSES,
    PERMISSION_OWNER,
    PLAN_CATALOG,
    POLICY_POOL,
    REFUND_STATUSES,
    CUSTOMER_ADMIN_EXTRA,
    CUSTOMER_ROLE_SET,
    ROLE_NAMES,
    SUPPORT_MANAGER_EXTRA,
    SUPPORT_ROLE_SET,
    SUPPORT_TIERS,
    SUBJECT_POOL,
    TENANT_ADMIN_COMPOSITE,
    TICKET_CATEGORIES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
)
from scripts.synthetic_data.scenarios import Scenario, get_scenarios

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _money(value: str | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _weighted_choice(rng: random.Random, choices: tuple[tuple[str, int], ...]) -> str:
    total = sum(weight for _, weight in choices)
    pick = rng.randrange(total)
    for value, weight in choices:
        pick -= weight
        if pick < 0:
            return value
    return choices[0][0]


def _rand_past(rng: random.Random, max_days: int = 365, min_days: int = 0) -> datetime:
    return utc_now() - timedelta(days=rng.uniform(min_days, max_days))


def _sha256_hex(payload: object) -> str:
    return _hash(payload)


_DOCUMENT_QUERY_HINTS = (
    ("退款", "退款政策是什么？重复扣费如何申请退款？"),
    ("SLA", "CloudDesk 的 SLA 支持等级和响应时间是什么？"),
    ("账户", "账户被锁定怎么办？如何修改密码和设置 MFA？"),
    ("计费", "账单和发票常见问题，如何修改发票信息？"),
    ("API", "API 如何集成？接口限流和 Webhook 事件说明。"),
    ("Webhook", "Webhook 回调失败如何排查和重试？"),
    ("故障", "服务故障如何处理？应急和升级流程。"),
    ("同步", "数据同步失败如何处置？"),
)


def _document_query(title: str) -> str:
    for hint, query in _DOCUMENT_QUERY_HINTS:
        if hint in title:
            return query
    return f"{title} 相关内容是什么？"


# ---------------------------------------------------------------------------
# Per-tenant seeding
# ---------------------------------------------------------------------------


class _TenantData:
    """Mutable bag of objects created for one tenant (used to resolve IDs)."""

    def __init__(self, tenant: Tenant) -> None:
        self.tenant = tenant
        self.roles: list[Role] = []
        self.users: list[User] = []
        self.customer_users: list[User] = []
        self.support_users: list[User] = []
        self.customers: list[Customer] = []
        self.payments: list[Payment] = []
        self.documents: list[Document] = []


def _build_roles_and_users(
    data: _TenantData,
    rng: random.Random,
    profile,
) -> None:
    tenant = data.tenant
    # One role row per role code.
    for code in ROLE_NAMES:
        data.roles.append(
            Role(
                tenant_id=tenant.id,
                code=code,
                name=ROLE_NAMES[code],
                status="active",
                is_platform_role=False,
            )
        )
    # Customer-side users (contacts) and support-side users.
    customer_count = max(1, int(profile.users_per_tenant * 0.6))
    support_count = max(1, profile.users_per_tenant - customer_count)
    seq = 0
    for _ in range(customer_count):
        seq += 1
        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=f"{tenant.slug}.user{seq}@example.com",
            display_name=f"客户用户{seq}",
            status="active",
            last_login_at=_rand_past(rng, 90, 1),
        )
        data.users.append(user)
        data.customer_users.append(user)
    for _ in range(support_count):
        seq += 1
        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=f"{tenant.slug}.staff{seq}@example.com",
            display_name=f"服务人员{seq}",
            status="active",
            last_login_at=_rand_past(rng, 30, 0),
        )
        data.users.append(user)
        data.support_users.append(user)


async def _seed_tenant(
    session: AsyncSession,
    tenant: Tenant,
    profile,
    rng: random.Random,
    scenario_pool: list[Scenario],
) -> None:
    """Insert every row belonging to a single tenant (dependency ordered)."""
    data = _TenantData(tenant)
    session.add(tenant)
    await session.flush()

    # --- identity: roles, users, permissions, assignments ---
    _build_roles_and_users(data, rng, profile)
    role_by_code = {role.code: role for role in data.roles}
    session.add_all(data.roles)
    session.add_all(data.users)
    await session.flush()
    user_roles: list[UserRole] = []
    permissions: list[Permission] = []
    for user in data.users:
        if user in data.customer_users:
            role_codes = set(CUSTOMER_ROLE_SET)
            if rng.random() < 0.2:
                role_codes.update(CUSTOMER_ADMIN_EXTRA)
        else:
            # Support staff always carry the customer-facing read role so the
            # ticket/conversation console works, plus operate roles.
            role_codes = set(SUPPORT_ROLE_SET)
            if rng.random() < 0.3:
                role_codes.update(SUPPORT_MANAGER_EXTRA)
            if rng.random() < 0.05:
                role_codes.update(TENANT_ADMIN_COMPOSITE)
        for role_code in role_codes:
            user_roles.append(
                UserRole(
                    tenant_id=tenant.id,
                    user_id=user.id,
                    role_id=role_by_code[role_code].id,
                )
            )
    for permission_code, owner_role in PERMISSION_OWNER.items():
        permissions.append(
            Permission(
                tenant_id=tenant.id,
                role_id=role_by_code[owner_role].id,
                code=permission_code,
                name=permission_code,
                status="active",
            )
        )
    session.add_all(user_roles)
    session.add_all(permissions)
    await session.flush()

    # --- customers + contacts ---
    for idx in range(profile.customers_per_tenant):
        customer = Customer(
            id=uuid4(),
            tenant_id=tenant.id,
            name=f"{tenant.name}客户{idx + 1}",
            external_customer_id=f"ext-cus-{tenant.slug}-{idx + 1}",
            support_tier=rng.choice(SUPPORT_TIERS),
            status=_weighted_choice(rng, CUSTOMER_STATUSES),
        )
        data.customers.append(customer)
        session.add(customer)
        await session.flush()
        contact_user = data.customer_users[idx % len(data.customer_users)]
        session.add(
            CustomerContact(
                id=uuid4(),
                tenant_id=tenant.id,
                customer_id=customer.id,
                user_id=contact_user.id,
                channel=rng.choice(("portal", "email", "phone")),
                masked_value=f"138****{rng.randint(1000, 9999)}",
                contact_hash=_sha256_hex(f"contact-{customer.id}"),
                preferred_language=rng.choice(("zh-CN", "zh-CN", "en-US")),
            )
        )
    await session.flush()

    # --- subscriptions ---
    subscriptions: list[Subscription] = []
    for idx in range(profile.subscriptions_per_tenant):
        customer = rng.choice(data.customers)
        plan_code, _, price, cycle = rng.choice(PLAN_CATALOG)
        status = _weighted_choice(
            rng,
            (("active", 78), ("trialing", 5), ("past_due", 7), ("canceled", 6), ("paused", 4)),
        )
        effective_from = _rand_past(rng, 400, 10)
        effective_until = (
            None
            if status in {"active", "trialing"}
            else effective_from + timedelta(days=rng.choice((30, 90, 365)))
        )
        sub = Subscription(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer.id,
            external_subscription_id=f"ext-sub-{tenant.slug}-{idx + 1}",
            plan_code=plan_code,
            status=status,
            billing_cycle=cycle,
            effective_from=effective_from,
            effective_until=effective_until,
        )
        subscriptions.append(sub)
        session.add(sub)
    await session.flush()

    # --- invoices ---
    invoices: list[Invoice] = []
    for idx in range(profile.payments_per_tenant):
        subscription = rng.choice(subscriptions)
        customer = subscription.customer_id
        plan_code, _, price, cycle = next(
            (p for p in PLAN_CATALOG if p[0] == subscription.plan_code), PLAN_CATALOG[0]
        )
        multiplier = 1 if cycle == "monthly" else (3 if cycle == "quarterly" else 12)
        amount = _money(price) * multiplier
        invoice_status = _weighted_choice(rng, INVOICE_STATUSES)
        invoice = Invoice(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer,
            subscription_id=subscription.id,
            external_invoice_id=f"ext-inv-{tenant.slug}-{idx + 1}",
            amount=amount,
            currency=CURRENCY,
            status=invoice_status,
            issued_at=_rand_past(rng, 120, 1),
        )
        invoices.append(invoice)
        session.add(invoice)
    await session.flush()

    # --- payments (only for invoiced/paid invoices, but keep volume consistent) ---
    payment_count = profile.payments_per_tenant
    payments: list[Payment] = []
    for idx in range(payment_count):
        invoice = invoices[idx % len(invoices)]
        status = _weighted_choice(rng, PAYMENT_STATUSES)
        payment = Payment(
            id=uuid4(),
            tenant_id=tenant.id,
            invoice_id=invoice.id,
            customer_id=invoice.customer_id,
            external_payment_id=f"ext-pay-{tenant.slug}-{idx + 1}",
            amount=invoice.amount,
            currency=CURRENCY,
            status=status,
            paid_at=invoice.issued_at + timedelta(minutes=rng.randint(1, 2880)),
        )
        payments.append(payment)
        session.add(payment)
    await session.flush()
    data.payments = payments

    # --- refunds (only against payments that could be refunded) ---
    refunds: list[Refund] = []
    for idx in range(profile.refunds_per_tenant):
        payment = payments[idx % len(payments)]
        status = _weighted_choice(rng, REFUND_STATUSES)
        requester = rng.choice(data.customer_users + data.support_users)
        refund = Refund(
            id=uuid4(),
            tenant_id=tenant.id,
            payment_id=payment.id,
            amount=payment.amount,
            reason=rng.choice(
                ("duplicate_charge", "service_not_rendered", "subscription_cancelled", "customer_request")
            ),
            status=status,
            idempotency_key=f"refund-{tenant.slug}-{idx + 1}",
            requested_by_user_id=requester.id,
            executed_at=None if status in {"requested", "pending"} else _rand_past(rng, 90, 1),
            has_unknown_execution=status == "unknown_execution_state",
        )
        refunds.append(refund)
        session.add(refund)
    await session.flush()

    # --- tickets (+ events, messages, assignments, approvals) ---
    await _seed_tickets(session, data, rng, profile, refunds)

    # --- conversations with scenario messages ---
    await _seed_conversations(session, data, rng, profile, scenario_pool)

    # --- policies, documents, memory, governance, runtime, audit, evaluation ---
    await _seed_policies(session, data)
    await _seed_documents(session, data, rng, profile)
    await _seed_memory_records(session, data, rng, profile)
    await _seed_governance(session, data)
    await _seed_runtime(session, data, rng)
    await _seed_audit_logs(session, data, rng)
    await _seed_evaluation(session, data, profile, scenario_pool)

    await session.flush()


async def _seed_tickets(
    session: AsyncSession,
    data: _TenantData,
    rng: random.Random,
    profile,
    refunds: list[Refund],
) -> None:
    tenant = data.tenant
    tickets: list[Ticket] = []
    events: list[TicketEvent] = []
    messages: list[TicketMessage] = []
    assignments: list[TicketAssignment] = []
    approvals: list[ApprovalRequest] = []
    approval_actions: list[ApprovalAction] = []

    from backend.domain.ticket import TicketStatus

    refund_by_payment: dict[UUID, Refund] = {}
    for refund in refunds:
        refund_by_payment.setdefault(refund.payment_id, refund)
    payment_ids = [payment.id for payment in data.payments]

    for idx in range(profile.tickets_per_tenant):
        customer = rng.choice(data.customers)
        assignee = rng.choice(data.support_users)
        status_value = _weighted_choice(rng, TICKET_STATUSES)
        final_status = TicketStatus(status_value)
        category = rng.choice(TICKET_CATEGORIES)
        priority = _weighted_choice(rng, TICKET_PRIORITIES)
        subject = rng.choice(SUBJECT_POOL)
        resolved_at = utc_now() - timedelta(days=rng.uniform(0, 30)) if final_status in {TicketStatus.RESOLVED, TicketStatus.CLOSED} else None

        ticket = Ticket(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer.id,
            subject=subject,
            description_summary=f"{subject}：{subject}相关的客户描述与处理记录。",
            category=category,
            priority=priority,
            status=final_status,
            current_assignee_id=assignee.id,
            resolved_at=resolved_at,
        )
        tickets.append(ticket)
        session.add(ticket)
        await session.flush()

        # Assignment record (assigned user must be an active support user).
        if final_status != TicketStatus.CANCELLED:
            assignments.append(
                TicketAssignment(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    ticket_id=ticket.id,
                    assigned_user_id=assignee.id,
                    assigned_by_user_id=rng.choice(data.support_users).id,
                    reason_summary="自动分配",
                    assigned_at=ticket.created_at or utc_now(),
                )
            )
        # Event trail following the ticket state machine.
        events.append(
            TicketEvent(
                id=uuid4(),
                tenant_id=tenant.id,
                ticket_id=ticket.id,
                actor_id=assignee.id,
                event_type="created",
                from_status=None,
                to_status=TicketStatus.OPEN,
                payload_summary={"category": category, "priority": priority},
            )
        )
        if final_status != TicketStatus.OPEN:
            try:
                transition_ticket(TicketStatus.OPEN, final_status)
            except InvalidStateTransition:
                pass
            else:
                events.append(
                    TicketEvent(
                        id=uuid4(),
                        tenant_id=tenant.id,
                        ticket_id=ticket.id,
                        actor_id=assignee.id,
                        event_type="status_change",
                        from_status=TicketStatus.OPEN,
                        to_status=final_status,
                        payload_summary={"reason": "workflow"},
                    )
                )
        # Messages: customer ask + agent reply.
        customer_author = rng.choice(data.customer_users)
        messages.append(
            TicketMessage(
                id=uuid4(),
                tenant_id=tenant.id,
                ticket_id=ticket.id,
                author_id=customer_author.id,
                body=f"关于{subject}，请协助处理。",
                visibility="public",
            )
        )
        messages.append(
            TicketMessage(
                id=uuid4(),
                tenant_id=tenant.id,
                ticket_id=ticket.id,
                author_id=assignee.id,
                body="已收到，正在为您核实并处理。",
                visibility="public",
            )
        )

        # Approval requests: pending_approval tickets and high-value refunds.
        if final_status == TicketStatus.PENDING_APPROVAL or rng.random() < 0.12:
            linked_refund = refund_by_payment.get(rng.choice(payment_ids))
            action = "refund.execute" if linked_refund is not None else "ticket.resolve"
            amount = linked_refund.amount if linked_refund is not None else None
            decided = rng.random() < 0.6
            decision = rng.choice(("approved", "rejected")) if decided else None
            approval = ApprovalRequest(
                id=uuid4(),
                tenant_id=tenant.id,
                ticket_id=ticket.id,
                refund_id=linked_refund.id if linked_refund is not None else None,
                requested_by_user_id=assignee.id,
                action=action,
                payload_summary={"subject": subject, "category": category},
                payload_hash=_sha256_hex({"ticket_id": str(ticket.id), "action": action}),
                amount=amount,
                risk_level="medium" if amount is None or amount < 500 else "high",
                approval_role="support_manager" if amount is None or amount < 5000 else "finance_reviewer",
                status=decision or "pending",
                expires_at=utc_now() + timedelta(days=2),
                checkpoint_reference=None,
            )
            approvals.append(approval)
            session.add(approval)
            await session.flush()
            if decision is not None:
                approval_actions.append(
                    ApprovalAction(
                        id=uuid4(),
                        tenant_id=tenant.id,
                        approval_request_id=approval.id,
                        actor_id=rng.choice(data.support_users).id,
                        action=decision,
                        reason="依据退款政策与证据进行审批",
                        changes_summary={},
                    )
                )
            else:
                # Pending approvals must reference a live workflow checkpoint
                # so resume_refund_after_approval can restore and revalidate
                # business state (spec: human-in-the-loop resume).
                checkpoint_thread = f"cp-{approval.id}"
                session.add(
                    WorkflowCheckpoint(
                        id=uuid4(),
                        tenant_id=tenant.id,
                        thread_id=checkpoint_thread,
                        state_summary={
                            "approval_request_id": str(approval.id),
                            "ticket_id": str(ticket.id),
                            "action": action,
                            "status": "pending_approval",
                        },
                        refund_idempotency_key=(
                            linked_refund.idempotency_key
                            if linked_refund is not None
                            else f"checkpoint-{approval.id}"
                        ),
                        status="pending_approval",
                        trace_id=None,
                    )
                )
                approval.checkpoint_reference = checkpoint_thread

    session.add_all(tickets)
    session.add_all(events)
    session.add_all(messages)
    session.add_all(assignments)
    session.add_all(approval_actions)


async def _seed_conversations(
    session: AsyncSession,
    data: _TenantData,
    rng: random.Random,
    profile,
    scenario_pool: list[Scenario],
) -> None:
    tenant = data.tenant
    used_scenario_codes: set[str] = set()
    # Dedicated scenario conversations: at most scenario_variants, each used once.
    for scenario in scenario_pool[: min(profile.scenario_variants, len(scenario_pool))]:
        if scenario["code"] in used_scenario_codes:
            continue
        used_scenario_codes.add(scenario["code"])
        user = rng.choice(data.customer_users)
        body = scenario["user_message"]
        if scenario["code"] == "oversized_input":
            body = ("超长问题占位内容。" * 40) + body
        conversation = Conversation(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=None,
            user_id=user.id,
            channel="portal",
            subject=scenario["subject"],
            status="open",
            started_at=_rand_past(rng, 60, 1),
        )
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationMessage(
                id=uuid4(),
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                author_id=user.id,
                author_type="user",
                role="user",
                body=body,
                visibility="public",
            )
        )
    # Generic business conversations.
    for _ in range(max(0, profile.conversations_per_tenant - len(used_scenario_codes))):
        user = rng.choice(data.customer_users)
        conversation = Conversation(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=None,
            user_id=user.id,
            channel=rng.choice(CONVERSATION_CHANNELS),
            subject=rng.choice(SUBJECT_POOL),
            status=_weighted_choice(rng, CONVERSATION_STATUSES),
            started_at=_rand_past(rng, 90, 1),
        )
        session.add(conversation)
        await session.flush()
        session.add(
            ConversationMessage(
                id=uuid4(),
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                author_id=user.id,
                author_type="user",
                role="user",
                body=f"关于{conversation.subject}，请协助处理，谢谢。",
                visibility="public",
            )
        )
        session.add(
            ConversationMessage(
                id=uuid4(),
                tenant_id=tenant.id,
                conversation_id=conversation.id,
                author_id=None,
                author_type="agent",
                role="assistant",
                body="您好，我正在为您核实相关情况，请稍候。",
                visibility="public",
            )
        )


async def _seed_policies(session: AsyncSession, data: _TenantData) -> None:
    tenant = data.tenant
    for policy_def in POLICY_POOL:
        policy = Policy(
            id=uuid4(),
            tenant_id=tenant.id,
            policy_code=policy_def["policy_code"],
            name=policy_def["name"],
            status="active",
            owner_team="customer_operations",
        )
        session.add(policy)
        await session.flush()
        session.add(
            PolicyVersion(
                id=uuid4(),
                tenant_id=tenant.id,
                policy_id=policy.id,
                version_number=1,
                status="published",
                content_summary=policy_def["content"],
                content_hash=_sha256_hex(policy_def["content"]),
                source_uri=f"policies://{policy_def['policy_code']}/v1",
                effective_from=_past_days(180),
                effective_to=None,
                published_at=_past_days(180),
            )
        )


def _past_days(days: int) -> datetime:
    return utc_now() - timedelta(days=days)


async def _seed_documents(session: AsyncSession, data: _TenantData, rng: random.Random, profile) -> None:
    tenant = data.tenant
    for idx in range(profile.documents_per_tenant):
        source_type, title_base = rng.choice(DOCUMENT_SOURCES)
        title = f"{title_base} {idx + 1}"
        visibility = rng.choice(DOCUMENT_VISIBILITIES)
        document = Document(
            id=uuid4(),
            tenant_id=tenant.id,
            external_document_id=f"ext-doc-{tenant.slug}-{idx + 1}",
            title=title,
            status="active",
            source_uri=f"docs://{tenant.slug}/{source_type}/{idx + 1}",
            visibility=visibility,
        )
        session.add(document)
        await session.flush()
        data.documents.append(document)
        chunks: list[KnowledgeChunk] = []
        content_lines = [
            f"# {title}",
            f"本文件属于 {source_type} 类型，适用于 {tenant.name}。",
            "CloudDesk 企业协作平台为客户提供账户、账单、技术支持与 SLA 服务。",
            "政策生效日期以最新发布版本为准，冲突时优先采纳当前生效版本。",
        ]
        for chunk_index, line in enumerate(content_lines):
            chunks.append(
                KnowledgeChunk(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    document_id=document.id,
                    chunk_number=chunk_index + 1,
                    content=line,
                    content_hash=_sha256_hex(line),
                    token_count=len(line),
                    status="active",
                )
            )
        session.add_all(chunks)
        session.add(
            DocumentVersion(
                id=uuid4(),
                tenant_id=tenant.id,
                document_id=document.id,
                version_number=1,
                content_hash=_sha256_hex("\n".join(content_lines)),
                object_uri=f"s3://knowledge/{tenant.slug}/{idx + 1}/v1",
                effective_from=_past_days(rng.randint(30, 300)),
                effective_to=None,
                chunk_count=len(chunks),
            )
        )


async def _seed_memory_records(session: AsyncSession, data: _TenantData, rng: random.Random, profile) -> None:
    tenant = data.tenant
    sources = ("conversation_extraction", "ticket_resolution", "customer_profile")
    for _ in range(profile.memories_per_tenant):
        memory_type = rng.choice(MEMORY_TYPES)
        user = rng.choice(data.customer_users + data.support_users)
        customer_uuid: UUID | None = None
        payload: dict[str, object] = {}
        if memory_type == "user":
            payload = {"preferred_language": "zh-CN", "timezone": "Asia/Shanghai", "notification": "email"}
        elif memory_type == "customer":
            customer = rng.choice(data.customers)
            customer_uuid = customer.id
            payload = {"support_tier": customer.support_tier, "preferred_channel": "portal"}
        else:
            payload = {"problem_type": "refund", "root_cause": "duplicate_charge", "verified": True}
        session.add(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant.id,
                memory_type=memory_type,
                payload_summary=payload,
                payload_hash=_sha256_hex(payload),
                source=rng.choice(sources),
                confidence=rng.uniform(0.7, 0.99),
                ttl_expires_at=utc_now() + timedelta(days=rng.randint(90, 360)),
                last_verified_at=_past_days(rng.randint(1, 60)),
                user_id=user.id if memory_type != "customer" else None,
                customer_id=customer_uuid,
            )
        )


async def _seed_governance(session: AsyncSession, data: _TenantData) -> None:
    tenant = data.tenant
    # Agents
    for agent_code, name in (("customer_service", "客服 Agent"), ("refund_agent", "退款 Agent"), ("knowledge_agent", "知识检索 Agent")):
        agent = AgentDefinition(
            id=uuid4(), tenant_id=tenant.id, agent_code=agent_code, name=name, status="active"
        )
        session.add(agent)
        await session.flush()
        session.add(
            AgentVersion(
                id=uuid4(),
                tenant_id=tenant.id,
                agent_id=agent.id,
                version_number=1,
                graph_reference=f"graph://{agent_code}/v1",
                config_summary={"model_profile": "balanced", "prompt_version": 1},
                status="published",
            )
        )
    # Prompts
    for prompt_code, name in (("support_intent", "意图识别"), ("support_response", "回复生成"), ("support_review", "质量审核")):
        prompt = PromptDefinition(
            id=uuid4(), tenant_id=tenant.id, prompt_code=prompt_code, name=name, status="active"
        )
        session.add(prompt)
        await session.flush()
        template = f"{name}提示词模板 v1"
        session.add(
            PromptVersion(
                id=uuid4(),
                tenant_id=tenant.id,
                prompt_id=prompt.id,
                version_number=1,
                template_summary=template,
                template_hash=_sha256_hex(template),
                status="published",
            )
        )
    # Model profiles
    for profile_code, provider, model_name in (
        ("fast", "openai-compatible", "fast-model"),
        ("balanced", "openai-compatible", "balanced-model"),
        ("reasoning", "openai-compatible", "reasoning-model"),
        ("reviewer", "openai-compatible", "reviewer-model"),
    ):
        session.add(
            ModelProfile(
                id=uuid4(),
                tenant_id=tenant.id,
                profile_code=profile_code,
                provider=provider,
                model_name=model_name,
                config_summary={"temperature": 0.3, "max_tokens": 2000},
                status="active",
            )
        )
    # Feature flags
    for flag_key, enabled, config in FEATURE_FLAGS:
        session.add(
            FeatureFlag(
                id=uuid4(),
                tenant_id=tenant.id,
                flag_key=flag_key,
                enabled=enabled,
                config_summary=config,
            )
        )


async def _seed_runtime(session: AsyncSession, data: _TenantData, rng: random.Random) -> None:
    tenant = data.tenant
    node_names = ("input_validator", "security_guard", "domain_guard", "customer_service", "knowledge_retrieval", "rule_engine", "response_generation", "ticket_writer")
    for idx in range(6):
        trace = RuntimeTrace(
            id=uuid4(),
            tenant_id=tenant.id,
            trace_key=f"trace-{tenant.slug}-{idx + 1}",
            status=rng.choice(("completed", "completed", "failed")),
            entrypoint="customer_consult",
            input_summary="客户咨询摘要（脱敏）",
            input_hash=_sha256_hex({"trace": idx, "tenant": str(tenant.id)}),
            total_input_tokens=rng.randint(300, 3000),
            total_output_tokens=rng.randint(100, 1200),
            total_cost=Decimal(str(rng.uniform(0.01, 0.5))).quantize(Decimal("0.001")),
            retry_count=rng.randint(0, 2),
            error_summary=None,
            started_at=_past_days(rng.randint(0, 30)),
            finished_at=None,
        )
        session.add(trace)
        await session.flush()
        for node_name in node_names:
            session.add(
                RuntimeSpan(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    trace_id=trace.id,
                    node_name=node_name,
                    status="completed",
                    input_summary=f"{node_name} 输入摘要",
                    output_summary=f"{node_name} 输出摘要",
                    started_at=trace.started_at,
                    finished_at=trace.started_at + timedelta(seconds=rng.randint(1, 20)),
                    duration_ms=rng.randint(50, 1500),
                )
            )
        session.add(
            ToolExecution(
                id=uuid4(),
                tenant_id=tenant.id,
                trace_id=trace.id,
                span_id=None,
                tool_name=rng.choice(("payment_lookup", "customer_lookup", "refund_create", "ticket_create")),
                status="completed",
                arguments_summary={"entity_type": "payment"},
                result_summary={"found": True},
                error_summary=None,
                retry_count=0,
                duration_ms=rng.randint(20, 800),
            )
        )
        session.add(
            WorkflowCheckpoint(
                id=uuid4(),
                tenant_id=tenant.id,
                thread_id=f"thread-{tenant.slug}-{idx + 1}",
                state_summary={"status": "completed", "nodes": len(node_names)},
                refund_idempotency_key=f"refund-{tenant.slug}-checkpoint-{idx + 1}",
                status="completed",
                trace_id=trace.id,
            )
        )


async def _seed_audit_logs(session: AsyncSession, data: _TenantData, rng: random.Random) -> None:
    tenant = data.tenant
    for idx in range(20):
        actor = rng.choice(data.support_users)
        session.add(
            AuditLog(
                id=uuid4(),
                tenant_id=tenant.id,
                actor_id=actor.id,
                action=rng.choice(("ticket.created", "refund.requested", "approval.approved", "conversation.started")),
                resource_type=rng.choice(("ticket", "refund", "approval", "conversation")),
                resource_id=None,
                metadata_summary={"synthetic": True, "seq": idx},
                metadata_hash=_sha256_hex({"synthetic": True, "seq": idx}),
            )
        )


async def _seed_evaluation(session: AsyncSession, data: _TenantData, profile, scenario_pool: list[Scenario]) -> None:
    tenant = data.tenant
    datasets: list[EvaluationDataset] = []
    for dataset_code, name in EVALUATION_DATASETS:
        dataset = EvaluationDataset(
            id=uuid4(), tenant_id=tenant.id, dataset_code=dataset_code, name=name, status="active"
        )
        session.add(dataset)
        await session.flush()
        datasets.append(dataset)

    # Weighted dataset distribution so retrieval cases (needed for RAG
    # evaluation) receive a meaningful share of the budget. Each dataset
    # gets weight/total of the budget; leftover cases go to retrieval.
    total_weight = sum(EVALUATION_DATASET_WEIGHTS)
    per_dataset_counts = [
        max(1, profile.evaluation_cases_per_tenant * weight // total_weight)
        for weight in EVALUATION_DATASET_WEIGHTS
    ]
    leftover = profile.evaluation_cases_per_tenant - sum(per_dataset_counts)
    if leftover > 0:
        retrieval_index = next(
            index
            for index, dataset in enumerate(datasets)
            if dataset.dataset_code == "retrieval"
        )
        per_dataset_counts[retrieval_index] += leftover
    scenario_count = len(scenario_pool)
    case_seq = 0
    for dataset, dataset_count in zip(datasets, per_dataset_counts):
        for _ in range(dataset_count):
            case_seq += 1
            if dataset.dataset_code == "retrieval" and data.documents:
                # Retrieval cases carry document_ids ground truth derived from
                # the tenant's own knowledge documents.
                document = data.documents[(case_seq - 1) % len(data.documents)]
                input_text = _document_query(document.title)
                expected = {"document_ids": [str(document.id)]}
                tags = ["retrieval", "synthetic"]
            else:
                scenario = scenario_pool[(case_seq - 1) % scenario_count]
                input_text = scenario["user_message"]
                expected = {
                    "tags": scenario["tags"],
                    "expectation": scenario["expectation"],
                }
                tags = list(scenario["tags"])
            session.add(
                EvaluationCase(
                    id=uuid4(),
                    tenant_id=tenant.id,
                    dataset_id=dataset.id,
                    case_key=f"{dataset.dataset_code}-{tenant.slug}-{case_seq}",
                    input_summary=input_text[:2000],
                    expected_summary=expected,
                    tags=tags,
                )
            )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def reset_database(database_url: str) -> None:
    """Truncate all tables (except alembic_version) keeping schema intact."""
    engine = create_async_engine(database_url, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            tables = sorted(Base.metadata.tables.keys())
            if "alembic_version" in tables:
                tables.remove("alembic_version")
            if not tables:
                return
            names = ", ".join(f'"{table}"' for table in tables)
            await connection.execute(text(f"TRUNCATE TABLE {names} CASCADE"))
    finally:
        await engine.dispose()


async def generate_all(
    *,
    database_url: str,
    profile,
    seed: int,
    tenant_prefix: str = "synthetic",
) -> dict[str, int]:
    engine = create_async_engine(database_url, pool_pre_ping=True, pool_size=5)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    counters: dict[str, int] = {}
    try:
        async with session_factory() as session:
            rng = random.Random(seed)
            scenario_pool = get_scenarios()
            for tenant_index in range(profile.tenants):
                tenant_slug = f"{tenant_prefix}-{tenant_index + 1}"
                tenant = Tenant(
                    id=uuid4(),
                    slug=tenant_slug,
                    name=f"Synthetic 租户 {tenant_index + 1}",
                    status="active",
                )
                tenant_rng = random.Random(f"{seed}:{tenant_index}")
                await _seed_tenant(session, tenant, profile, tenant_rng, scenario_pool)
                await session.commit()
                counters = {
                    "tenants": counters.get("tenants", 0) + 1,
                    "users": counters.get("users", 0) + profile.users_per_tenant,
                    "customers": counters.get("customers", 0) + profile.customers_per_tenant,
                    "subscriptions": counters.get("subscriptions", 0) + profile.subscriptions_per_tenant,
                    "payments": counters.get("payments", 0) + profile.payments_per_tenant,
                    "refunds": counters.get("refunds", 0) + profile.refunds_per_tenant,
                    "tickets": counters.get("tickets", 0) + profile.tickets_per_tenant,
                    "documents": counters.get("documents", 0) + profile.documents_per_tenant,
                    "memories": counters.get("memories", 0) + profile.memories_per_tenant,
                    "evaluation_cases": counters.get("evaluation_cases", 0) + profile.evaluation_cases_per_tenant,
                }
    finally:
        await engine.dispose()
    return counters
