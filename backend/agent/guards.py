from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


GuardStatus = Literal["allow", "block", "human_handoff"]
DomainStatus = Literal["in_scope", "out_of_scope", "needs_clarification"]
DomainName = Literal[
    "billing",
    "account",
    "technical",
    "sla",
    "ticket",
    "knowledge",
    "customer_service",
]


class GuardDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: GuardStatus
    code: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=120)


class DomainDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: DomainStatus
    domain: DomainName
    reason: str = Field(min_length=1, max_length=120)


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold()


class InputSecurityGuard:
    """Deterministic input boundary; it never includes matched input in output."""

    MAX_INPUT_LENGTH = 2000
    _prompt_injection_patterns = (
        "ignore previous instructions",
        "ignore all previous instructions",
        "忽略之前指令",
        "忽略以上指令",
        "忘记之前的指令",
        "system prompt",
        "系统提示词",
        "泄露系统指令",
    )
    _credential_patterns = (
        re.compile(r"\bsk-[a-z0-9][a-z0-9_-]{7,}\b"),
        re.compile(r"\bbearer\s+[a-z0-9._-]{8,}\b"),
        re.compile(r"(?:api[\s_-]?key|password|passwd|secret|token)\s*[:=]\s*\S+"),
        re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
    )
    _unsafe_action_patterns = (
        "绕过审批",
        "跳过审批",
        "bypass approval",
        "skip approval",
        "绕过租户隔离",
        "bypass tenant isolation",
        "未授权工具",
        "unauthorized tool",
        "未经授权执行",
    )
    _data_exfiltration_patterns = (
        "所有客户",
        "全部客户",
        "所有账单",
        "全部账单",
        "批量导出",
        "导出所有",
        "所有用户的数据",
        "别人的数据",
        "其他客户的数据",
    )

    def evaluate(self, text: str) -> GuardDecision:
        normalized = _normalize(text or "")
        if len(text or "") > self.MAX_INPUT_LENGTH:
            return GuardDecision(
                status="block",
                code="input_too_long",
                reason="输入长度超过安全限制",
            )
        if any(pattern in normalized for pattern in self._prompt_injection_patterns):
            return GuardDecision(
                status="block",
                code="prompt_injection",
                reason="检测到不允许的指令覆盖请求",
            )
        if any(pattern.search(normalized) for pattern in self._credential_patterns):
            return GuardDecision(
                status="block",
                code="credential_exposure",
                reason="检测到敏感凭据或支付信息",
            )
        if any(pattern in normalized for pattern in self._data_exfiltration_patterns):
            return GuardDecision(
                status="block",
                code="data_exfiltration",
                reason="检测到跨租户/批量数据索取",
            )
        if any(pattern in normalized for pattern in self._unsafe_action_patterns):
            return GuardDecision(
                status="human_handoff",
                code="unsafe_action_request",
                reason="该操作需要人工安全审核",
            )
        return GuardDecision(status="allow", code="input_allowed", reason="输入安全检查通过")


class DomainGuard:
    """Deterministic classifier for the supported CloudDesk business boundary."""

    _out_of_scope_patterns = (
        "真实生产环境的资金",
        "真实生产环境资金",
        "生产环境的资金",
        "生产环境资金",
        "真实生产环境的转账",
        "真实生产环境转账",
        "真实转账",
        "实际转账",
        "不属于clouddesk",
        "clouddesk以外",
        "其他平台",
        "外部系统",
    )
    _domain_keywords: tuple[tuple[DomainName, tuple[str, ...]], ...] = (
        (
            "billing",
            ("退款", "退费", "扣费", "账单", "支付", "发票", "订阅", "充值", "审批"),
        ),
        ("account", ("登录", "登陆", "密码", "mfa", "成员", "权限", "账户锁定", "账号锁定")),
        ("technical", ("api", "webhook", "同步", "上传", "服务不可用", "性能", "接口")),
        ("sla", ("sla", "支持等级", "赔偿", "紧急事件", "服务等级")),
        ("ticket", ("工单", "投诉", "故障单", "催办", "转派")),
        ("knowledge", ("知识库", "知识", "政策", "sop", "如何使用", "怎么查")),
        (
            "customer_service",
            ("你好", "您好", "嗨", "客服", "客户咨询", "一般说明", "帮助", "转人工", "人工客服", "人工", "转接", "真人"),
        ),
    )

    def evaluate(self, text: str) -> DomainDecision:
        normalized = _normalize(text or "")
        if not normalized:
            return DomainDecision(
                status="in_scope",
                domain="customer_service",
                reason="业务范围检查通过",
            )
        if any(pattern in normalized for pattern in self._out_of_scope_patterns):
            return DomainDecision(
                status="out_of_scope",
                domain="customer_service",
                reason="请求超出当前平台支持范围",
            )
        for domain, keywords in self._domain_keywords:
            if any(keyword in normalized for keyword in keywords):
                return DomainDecision(status="in_scope", domain=domain, reason="请求属于平台支持范围")
        return DomainDecision(
            status="needs_clarification",
            domain="customer_service",
            reason="请补充具体业务场景",
        )


__all__ = [
    "DomainDecision",
    "DomainGuard",
    "DomainName",
    "DomainStatus",
    "GuardDecision",
    "GuardStatus",
    "InputSecurityGuard",
]
