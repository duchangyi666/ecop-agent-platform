/** Formatting helpers and domain value -> Chinese label maps. */

const TICKET_STATUS: Record<string, string> = {
  open: "待处理",
  in_progress: "处理中",
  pending_customer: "等待客户",
  pending_approval: "等待审批",
  escalated: "已升级",
  resolved: "已解决",
  closed: "已关闭",
  reopened: "已重开",
  cancelled: "已取消",
};

const TICKET_PRIORITY: Record<string, string> = {
  low: "低",
  normal: "普通",
  medium: "中",
  high: "高",
  urgent: "紧急",
};

const APPROVAL_STATUS: Record<string, string> = {
  pending: "待审批",
  approved: "已批准",
  rejected: "已拒绝",
  modified: "已修改",
  expired: "已过期",
  more_information_required: "待补充",
};

const RISK_LEVEL: Record<string, string> = {
  low: "低风险",
  medium: "中风险",
  high: "高风险",
  critical: "严重",
};

const CONVERSATION_STATUS: Record<string, string> = {
  open: "进行中",
  in_progress: "处理中",
  pending_customer: "等待客户",
  escalated: "已升级",
  resolved: "已解决",
  closed: "已关闭",
  cancelled: "已取消",
};

const TICKET_CATEGORY: Record<string, string> = {
  billing: "账单",
  account: "账户",
  technical: "技术支持",
  sla: "SLA",
  ticket_ops: "工单运营",
};

const REFUND_STATUS: Record<string, string> = {
  requested: "已申请",
  pending: "处理中",
  succeeded: "已退款",
  rejected: "已拒绝",
  failed: "失败",
  unknown_execution_state: "状态未知",
};

export function ticketStatus(value: string | null | undefined): string {
  return value ? (TICKET_STATUS[value] ?? value) : "-";
}

export function ticketPriority(value: string | null | undefined): string {
  return value ? (TICKET_PRIORITY[value] ?? value) : "-";
}

export function approvalStatus(value: string | null | undefined): string {
  return value ? (APPROVAL_STATUS[value] ?? value) : "-";
}

export function riskLevel(value: string | null | undefined): string {
  return value ? (RISK_LEVEL[value] ?? value) : "-";
}

export function conversationStatus(value: string | null | undefined): string {
  return value ? (CONVERSATION_STATUS[value] ?? value) : "-";
}

export function ticketCategory(value: string | null | undefined): string {
  return value ? (TICKET_CATEGORY[value] ?? value) : "-";
}

export function refundStatus(value: string | null | undefined): string {
  return value ? (REFUND_STATUS[value] ?? value) : "-";
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function formatMoney(value: string | number | null | undefined, currency = "¥"): string {
  if (value === null || value === undefined) return "-";
  const numeric = Number(value);
  if (Number.isNaN(numeric)) return String(value);
  return `${currency}${numeric.toFixed(2)}`;
}
