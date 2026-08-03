"""Scale profiles, role catalog and business constants for synthetic data."""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Scale profiles
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScaleProfile:
    """Per-tenant and global generation counts. Globals sum across tenants."""

    tenants: int
    users_per_tenant: int
    customers_per_tenant: int
    subscriptions_per_tenant: int
    payments_per_tenant: int
    refunds_per_tenant: int
    tickets_per_tenant: int
    documents_per_tenant: int
    memories_per_tenant: int
    evaluation_cases_per_tenant: int
    conversations_per_tenant: int
    scenario_variants: int  # number of distinct injection scenarios distributed


SMALL = ScaleProfile(
    tenants=10,
    users_per_tenant=60,
    customers_per_tenant=20,
    subscriptions_per_tenant=30,
    payments_per_tenant=120,
    refunds_per_tenant=25,
    tickets_per_tenant=60,
    documents_per_tenant=8,
    memories_per_tenant=25,
    evaluation_cases_per_tenant=100,
    conversations_per_tenant=30,
    scenario_variants=24,
)

FULL = ScaleProfile(
    tenants=50,
    users_per_tenant=1000,
    customers_per_tenant=200,
    subscriptions_per_tenant=400,
    payments_per_tenant=2000,
    refunds_per_tenant=400,
    tickets_per_tenant=1000,
    documents_per_tenant=6,
    memories_per_tenant=100,
    evaluation_cases_per_tenant=20,
    conversations_per_tenant=200,
    scenario_variants=24,
)

SCALE_PROFILES = {"small": SMALL, "full": FULL}

# ---------------------------------------------------------------------------
# Roles and permissions
# ---------------------------------------------------------------------------

PERMISSION_CODES = (
    "customer.consult",
    "conversation.create",
    "conversation.read",
    "conversation.write",
    "ticket.create",
    "ticket.read",
    "ticket.update",
    "refund.request",
    "refund.approve",
    "approval.read",
    "knowledge.search",
    "knowledge.ingest",
    "knowledge.delete",
    "evaluation.read",
    "evaluation.run",
    "runtime.read",
)

# The permission model scopes each code to a single role per tenant
# (UniqueConstraint on tenant_id + code). PERMISSION_OWNER assigns each code
# to the role that carries it; users gain access through their user_roles.
PERMISSION_OWNER: dict[str, str] = {
    # customer-facing capabilities
    "customer.consult": "customer_user",
    "conversation.create": "customer_user",
    "conversation.read": "customer_user",
    "conversation.write": "customer_user",
    "ticket.read": "customer_user",
    "approval.read": "customer_admin",
    # support delivery
    "ticket.create": "support_agent",
    "ticket.update": "support_agent",
    "knowledge.search": "support_agent",
    "refund.request": "support_agent",
    "runtime.read": "support_agent",
    # management / review
    "knowledge.ingest": "support_manager",
    "knowledge.delete": "support_manager",
    "refund.approve": "support_manager",
    "evaluation.read": "support_manager",
    "evaluation.run": "finance_reviewer",
}

# A user holding one of these roles is additionally granted the support
# roles listed, approximating platform-wide access within the RBAC model.
TENANT_ADMIN_COMPOSITE = ("support_manager", "finance_reviewer", "customer_admin")

ROLE_NAMES = {
    "customer_user": "客户用户",
    "customer_admin": "客户管理员",
    "support_agent": "客服专员",
    "support_manager": "客服主管",
    "finance_reviewer": "财务复核",
    "technical_engineer": "技术支持工程师",
    "tenant_admin": "租户管理员",
}

# Platform users are assigned support-side roles; customer-side users get
# customer roles. A small fraction of support users get tenant_admin.
CUSTOMER_ROLES = ("customer_user", "customer_admin")
SUPPORT_ROLES = ("support_agent", "support_manager", "finance_reviewer", "technical_engineer")

# ---------------------------------------------------------------------------
# SaaS plan catalog
# ---------------------------------------------------------------------------

# (plan_code, plan_name, price_per_billing_cycle, cycle)
PLAN_CATALOG = (
    ("clouddesk-basic", "CloudDesk 基础版", "99.00", "monthly"),
    ("clouddesk-pro", "CloudDesk 专业版", "299.00", "monthly"),
    ("clouddesk-business", "CloudDesk 企业版", "899.00", "monthly"),
    ("clouddesk-enterprise", "CloudDesk 旗舰版", "2999.00", "monthly"),
)

# ---------------------------------------------------------------------------
# Domain value pools
# ---------------------------------------------------------------------------

CURRENCY = "CNY"

SUPPORT_TIERS = ("standard", "premium", "enterprise")

CUSTOMER_STATUSES = (
    ("active", 70),
    ("trial", 10),
    ("past_due", 12),
    ("suspended", 8),
)

# (invoice_status, weight)
INVOICE_STATUSES = (
    ("issued", 8),
    ("paid", 70),
    ("failed", 8),
    ("void", 6),
    ("overdue", 8),
)

# (payment_status, weight)  values from backend.domain.billing.PaymentStatus
PAYMENT_STATUSES = (
    ("succeeded", 85),
    ("failed", 7),
    ("requires_action", 5),
    ("unknown", 3),
)

# (refund_status, weight)  values from backend.domain.billing.RefundStatus
REFUND_STATUSES = (
    ("succeeded", 58),
    ("rejected", 16),
    ("pending", 9),
    ("requested", 6),
    ("failed", 7),
    ("unknown_execution_state", 4),
)

# (ticket_status, weight)  values from backend.domain.ticket.TicketStatus
TICKET_STATUSES = (
    ("resolved", 46),
    ("closed", 22),
    ("open", 10),
    ("in_progress", 8),
    ("pending_customer", 6),
    ("pending_approval", 3),
    ("escalated", 3),
    ("reopened", 1),
    ("cancelled", 1),
)

TICKET_CATEGORIES = ("billing", "account", "technical", "sla", "ticket_ops")

# (priority, weight)
TICKET_PRIORITIES = (
    ("low", 15),
    ("normal", 55),
    ("high", 20),
    ("urgent", 10),
)

CONVERSATION_STATUSES = (
    ("open", 30),
    ("in_progress", 20),
    ("pending_customer", 10),
    ("escalated", 5),
    ("resolved", 30),
    ("closed", 5),
)

CONVERSATION_CHANNELS = ("portal", "portal", "email", "email", "api")

MEMORY_TYPES = ("user", "customer", "solution")

DOCUMENT_VISIBILITIES = ("internal", "internal", "customer_facing")

POLICY_POOL = (
    {
        "policy_code": "refund_duplicate_charge",
        "name": "重复扣费退款政策",
        "content": {
            "scope": "重复扣费导致的重复支付可申请退款",
            "auto_execute_max": 500,
            "manager_approval_max": 5000,
            "finance_approval_above": 5000,
            "max_payment_interval_minutes": 30,
            "already_refunded_action": "reject",
            "evidence_required": ["payment_id", "occurred_at", "charge_amount"],
        },
    },
    {
        "policy_code": "refund_general",
        "name": "一般退款政策",
        "content": {
            "scope": "订阅取消或服务未提供时的退款",
            "refund_window_days": 7,
            "auto_execute_max": 200,
            "manager_approval_max": 3000,
            "pro_rata": True,
        },
    },
    {
        "policy_code": "sla_standard",
        "name": "标准支持 SLA",
        "content": {
            "first_response_minutes": 30,
            "severity_critical_resolve_hours": 8,
            "severity_high_resolve_hours": 24,
            "support_hours": "business_hours",
        },
    },
    {
        "policy_code": "sla_premium",
        "name": "高级支持 SLA",
        "content": {
            "first_response_minutes": 15,
            "severity_critical_resolve_hours": 4,
            "severity_high_resolve_hours": 12,
            "support_hours": "24x7",
        },
    },
    {
        "policy_code": "account_lock",
        "name": "账户锁定与解锁政策",
        "content": {
            "lock_after_failed_attempts": 5,
            "admin_unlock_required": True,
            "mfa_recovery": "support_agent",
        },
    },
    {
        "policy_code": "data_export",
        "name": "数据导出审批政策",
        "content": {
            "requires_approval_above_records": 5000,
            "approval_role": "tenant_admin",
            "export_format": ["csv", "json"],
        },
    },
)

DOCUMENT_SOURCES = (
    ("policy", "退款政策文档"),
    ("policy", "SLA 支持等级文档"),
    ("faq", "账户与安全常见问题"),
    ("faq", "计费与发票常见问题"),
    ("product", "API 集成手册"),
    ("product", "Webhook 事件说明"),
    ("runbook", "服务故障应急手册"),
    ("runbook", "数据同步失败处置手册"),
)

EVALUATION_DATASETS = (
    ("domain_classification", "业务范围分类"),
    ("intent_classification", "意图识别"),
    ("entity_extraction", "实体抽取"),
    ("security_detection", "安全风险检测"),
    ("retrieval", "知识检索"),
    ("refund_decision", "退款决策"),
    ("out_of_scope", "范围外问题"),
    ("response_quality", "回复质量"),
)

# Relative weight of each dataset when distributing evaluation cases.
# Retrieval gets a large share because RAG metrics need a real ground truth.
EVALUATION_DATASET_WEIGHTS = (10, 10, 8, 12, 40, 10, 5, 5)

FEATURE_FLAGS = (
    ("auto_refund", True, {"max_amount": "500.00"}),
    ("long_term_memory", True, {"ttl_days": 180}),
    ("hybrid_retrieval", True, {"dense_weight": 0.7, "sparse_weight": 0.3}),
    ("cross_encoder_rerank", False, {"model": "bge-reranker-large"}),
    ("prompt_v2", False, {"prompt_code": "support_v2"}),
)

# Generic subject/body pools used to build realistic ticket & conversation text.
SUBJECT_POOL = (
    "账单重复扣费",
    "退款申请",
    "支付失败",
    "发票信息需要修改",
    "订阅套餐降级",
    "登录失败次数过多",
    "账户被锁定",
    "MFA 验证码收不到",
    "重置密码",
    "添加新成员",
    "成员权限不正确",
    "API 返回 429 限流",
    "Webhook 回调失败",
    "数据同步长时间未完成",
    "服务间歇性不可用",
    "文件上传失败",
    "SLA 支持等级查询",
    "故障升级申请",
    "工单状态查询",
    "催办工单",
    "关闭工单",
    "发票抬头变更",
    "导出失败",
    "第三方集成连接失败",
)
