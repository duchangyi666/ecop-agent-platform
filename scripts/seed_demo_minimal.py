"""Seed a minimal, anonymised demo dataset for local walkthroughs.

Creates (idempotently):
- tenant `clouddesk` + user `demo@clouddesk.local` with all demo permissions
- customer `演示客户（脱敏）` linked to that user
- invoices + payments, including a duplicate pair for the refund scenario
- one open ticket
- three knowledge documents for RAG

Usage:
    python scripts/seed_demo_minimal.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import get_settings
from backend.database.base import TenantScope
from backend.database.models.billing import Customer, CustomerContact, Invoice, Payment
from backend.database.models.identity import Tenant, User
from backend.database.models.support import Ticket, TicketMessage
from backend.domain.billing import PaymentStatus
from backend.domain.ticket import TicketStatus
from backend.rag.config import get_rag_settings
from backend.rag.ingestion import KnowledgeIngestRequest, KnowledgeIngestService
from backend.rag.vector_store import create_knowledge_vector_store
from scripts.seed_demo_identity import SUPPORTED_PERMISSIONS, seed_demo_identity

TENANT_SLUG = "clouddesk"
USER_EMAIL = "demo@clouddesk.local"
CUSTOMER_EXTERNAL_ID = "demo-cust-001"


async def _ensure_identity(session) -> tuple[Tenant, User]:
    tenant = await session.scalar(select(Tenant).where(Tenant.slug == TENANT_SLUG))
    if tenant is None:
        tenant = Tenant(id=uuid4(), slug=TENANT_SLUG, name="CloudDesk 演示租户", status="active")
        session.add(tenant)
        await session.flush()
    user = await session.scalar(
        select(User).where(User.tenant_id == tenant.id, User.email == USER_EMAIL)
    )
    if user is None:
        user = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=USER_EMAIL,
            display_name="演示管理员",
            status="active",
        )
        session.add(user)
        await session.flush()
    return tenant, user


async def _ensure_customer(session, tenant: Tenant, user: User) -> Customer:
    customer = await session.scalar(
        select(Customer).where(
            Customer.tenant_id == tenant.id,
            Customer.external_customer_id == CUSTOMER_EXTERNAL_ID,
        )
    )
    if customer is None:
        customer = Customer(
            id=uuid4(),
            tenant_id=tenant.id,
            name="演示客户（脱敏）",
            external_customer_id=CUSTOMER_EXTERNAL_ID,
            support_tier="enterprise",
            status="active",
        )
        session.add(customer)
        await session.flush()
    contact = await session.scalar(
        select(CustomerContact).where(
            CustomerContact.tenant_id == tenant.id,
            CustomerContact.customer_id == customer.id,
            CustomerContact.user_id == user.id,
        )
    )
    if contact is None:
        session.add(
            CustomerContact(
                id=uuid4(),
                tenant_id=tenant.id,
                customer_id=customer.id,
                user_id=user.id,
                channel="email",
                masked_value="de***@demo.local",
                contact_hash=hashlib.sha256(USER_EMAIL.encode("utf-8")).hexdigest(),
                preferred_language="zh-CN",
            )
        )
    return customer


async def _ensure_payment(
    session,
    tenant: Tenant,
    customer: Customer,
    *,
    external_payment_id: str,
    amount: Decimal,
    paid_at: datetime,
    invoice_id: UUID | None = None,
) -> Payment:
    payment = await session.scalar(
        select(Payment).where(
            Payment.tenant_id == tenant.id,
            Payment.external_payment_id == external_payment_id,
        )
    )
    if payment is not None:
        if invoice_id is not None and payment.invoice_id != invoice_id:
            raise ValueError("existing demo payment belongs to a different invoice; use a fresh demo database")
        return payment
    invoice = None
    if invoice_id is not None:
        invoice = await session.scalar(select(Invoice).where(
            Invoice.id == invoice_id, Invoice.tenant_id == tenant.id, Invoice.customer_id == customer.id,
        ))
        if invoice is None:
            raise ValueError("demo invoice not found for customer")
    else:
        invoice = await session.scalar(select(Invoice).where(
            Invoice.tenant_id == tenant.id, Invoice.external_invoice_id == f"inv-{external_payment_id}",
        ))
    if invoice is None:
        invoice = Invoice(
            id=uuid4(),
            tenant_id=tenant.id,
            customer_id=customer.id,
            subscription_id=None,
            external_invoice_id=f"inv-{external_payment_id}",
            amount=amount,
            currency="CNY",
            status="issued",
            issued_at=paid_at,
        )
        session.add(invoice)
        await session.flush()
    payment = Payment(
        id=uuid4(),
        tenant_id=tenant.id,
        invoice_id=invoice.id,
        customer_id=customer.id,
        external_payment_id=external_payment_id,
        amount=amount,
        currency="CNY",
        status=PaymentStatus.SUCCEEDED,
        paid_at=paid_at,
    )
    session.add(payment)
    await session.flush()
    return payment


async def _ensure_ticket(session, tenant: Tenant, customer: Customer, user: User) -> Ticket:
    subject = "演示工单：账单金额与扣费疑问"
    ticket = await session.scalar(
        select(Ticket).where(Ticket.tenant_id == tenant.id, Ticket.subject == subject)
    )
    if ticket is not None:
        return ticket
    ticket = Ticket(
        id=uuid4(),
        tenant_id=tenant.id,
        customer_id=customer.id,
        subject=subject,
        description_summary="客户反馈本月账单出现两笔相同金额扣费，需要核对。",
        category="billing",
        priority="high",
        status=TicketStatus.IN_PROGRESS,
        current_assignee_id=user.id,
    )
    session.add(ticket)
    await session.flush()
    session.add(
        TicketMessage(
            id=uuid4(),
            tenant_id=tenant.id,
            ticket_id=ticket.id,
            author_id=user.id,
            body="您好，我发现本月有两笔相同金额的扣费，请帮我核对是否重复扣款。",
            visibility="public",
        )
    )
    return ticket


KNOWLEDGE_DOCS = [
    {
        "external_document_id": "demo-kb-refund",
        "title": "退款政策与到账说明",
        "content": (
            "CloudDesk 退款政策：客户在发现重复扣费、计费错误或服务未交付时，可以提交退款申请。"
            "系统会核对最近的成功支付记录，若在 24 小时内出现两笔金额相同的扣费，可认定为重复扣费并进入退款流程。"
            "退款金额大于等于 1000 元时，需要财务经理人工审批；低于 1000 元且支付状态正常时，可按低风险流程处理。"
            "审批通过后，退款申请进入执行队列，原路退回通常需要 3 到 5 个工作日，具体到账时间以支付渠道为准。"
            "退款申请提交后，客户可以在“我的工单”或退款记录中查看状态。"
        ),
    },
    {
        "external_document_id": "demo-kb-sla",
        "title": "企业版 SLA 与支持等级",
        "content": (
            "CloudDesk 企业版提供三档支持等级：标准、优先和关键业务保障。"
            "标准支持的工作时间为工作日 9:00 至 18:00，P2 问题 8 小时内响应；"
            "优先支持覆盖 7×24 小时，P1 问题 1 小时内响应；"
            "关键业务保障提供专属技术客户经理，P0 故障 15 分钟内响应，并每 30 分钟同步进展。"
            "SLA 赔偿仅适用于平台可用性低于承诺阈值的情况，需由客户成功团队审核后发放服务抵扣券，不直接退还现金。"
        ),
    },
    {
        "external_document_id": "demo-kb-invoice",
        "title": "发票开具与信息修改规则",
        "content": (
            "客户可以在管理控制台的账单页面申请开具增值税普通发票或专用发票。"
            "开票信息包括企业名称、纳税人识别号、注册地址、电话、开户行及账号。"
            "发票申请提交后，电子发票通常在 1 个工作日内开具并发送至预留邮箱；纸质专用发票需要 5 到 7 个工作日寄出。"
            "如需修改已开具发票的抬头或税号，请在开票后 30 天内联系客服，并提供加盖公章的说明材料。"
            "跨月红冲或重开需要财务审核，可能影响原发票的抵扣状态。"
        ),
    },
]


async def _seed_knowledge(session_factory, scope: TenantScope) -> None:
    vector_store = None
    try:
        vector_store = create_knowledge_vector_store(get_rag_settings())
    except Exception as exc:  # noqa: BLE001 - Milvus is optional
        print(f"milvus unavailable, indexing to postgres only: {exc}")
    service = KnowledgeIngestService(session_factory, vector_store=vector_store)
    # Fresh thread id per run: runtime_traces has a (tenant_id, trace_key) unique
    # constraint, while the document itself is upserted and versioned.
    run_suffix = uuid4().hex[:8]
    try:
        for doc in KNOWLEDGE_DOCS:
            request = KnowledgeIngestRequest(
                thread_id=f"seed-{doc['external_document_id']}-{run_suffix}",
                external_document_id=doc["external_document_id"],
                title=doc["title"],
                source_uri=f"demo://knowledge/{doc['external_document_id']}",
                visibility="tenant",
                content=doc["content"],
            )
            try:
                result = await service.run(scope=scope, request=request)
            except Exception as exc:  # noqa: BLE001 - retry without vector store
                print(f"vector ingest failed for {doc['external_document_id']}: {exc}")
                fallback = KnowledgeIngestService(session_factory, vector_store=None)
                result = await fallback.run(scope=scope, request=request)
            print(
                f"knowledge {doc['external_document_id']}: chunks={result.chunk_count} "
                f"vector={result.vector_indexed}"
            )
    finally:
        if vector_store is not None:
            await vector_store.close()


async def main() -> None:
    url = os.getenv("DATABASE_URL", get_settings().database_url)
    engine = create_async_engine(url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            tenant, user = await _ensure_identity(session)
            customer = await _ensure_customer(session, tenant, user)
            now = datetime.now(timezone.utc)
            pay_old = await _ensure_payment(
                session,
                tenant,
                customer,
                external_payment_id="demo-pay-old-99",
                amount=Decimal("99.00"),
                paid_at=now - timedelta(days=12),
            )
            pay_dup_a = await _ensure_payment(
                session,
                tenant,
                customer,
                external_payment_id="demo-pay-dup-1280-a",
                amount=Decimal("1280.00"),
                paid_at=now - timedelta(hours=6),
            )
            pay_dup_b = await _ensure_payment(
                session,
                tenant,
                customer,
                external_payment_id="demo-pay-dup-1280-b",
                amount=Decimal("1280.00"),
                paid_at=now - timedelta(hours=2),
                invoice_id=pay_dup_a.invoice_id,
            )
            ticket = await _ensure_ticket(session, tenant, customer, user)
            await session.commit()
            print(f"tenant_id={tenant.id}")
            print(f"user_id={user.id}")
            print(f"customer_id={customer.id}")
            print(f"ticket_id={ticket.id}")
            print(f"payment_old_id={pay_old.id}")
            print(f"payment_duplicate_ids={pay_dup_a.id},{pay_dup_b.id}")

        await seed_demo_identity(
            database_url=url,
            tenant_id=tenant.id,
            user_id=user.id,
            permission_codes=set(SUPPORTED_PERMISSIONS),
        )
        await _seed_knowledge(factory, TenantScope(tenant_id=tenant.id, actor_id=user.id, actor_type="user"))
        print("demo dataset ready")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
