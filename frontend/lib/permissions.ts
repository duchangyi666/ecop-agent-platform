export const PERMISSIONS = {
  CUSTOMER_CONSULT: "customer.consult",
  CONVERSATION_CREATE: "conversation.create",
  CONVERSATION_READ: "conversation.read",
  CONVERSATION_WRITE: "conversation.write",
  TICKET_CREATE: "ticket.create",
  TICKET_READ: "ticket.read",
  TICKET_UPDATE: "ticket.update",
  REFUND_REQUEST: "refund.request",
  REFUND_APPROVE: "refund.approve",
  APPROVAL_READ: "approval.read",
  KNOWLEDGE_SEARCH: "knowledge.search",
  KNOWLEDGE_INGEST: "knowledge.ingest",
  KNOWLEDGE_DELETE: "knowledge.delete",
  EVALUATION_READ: "evaluation.read",
  EVALUATION_RUN: "evaluation.run",
  RUNTIME_READ: "runtime.read",
} as const;

export type Permission = (typeof PERMISSIONS)[keyof typeof PERMISSIONS];
