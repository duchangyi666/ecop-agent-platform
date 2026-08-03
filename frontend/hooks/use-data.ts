"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ApprovalActionRequest,
  ApprovalDetailResponse,
  ApprovalListResponse,
  AuthTokenResponse,
  ConversationCreateRequest,
  ConversationDetailResponse,
  ConversationListResponse,
  ConversationMessageCreateRequest,
  CustomerConsultationResponse,
  EvaluationRunListResponse,
  EvaluationRunRequest,
  EvaluationRunResponse,
  KnowledgeDeleteResponse,
  KnowledgeDocumentListResponse,
  KnowledgeIngestRequest,
  KnowledgeIngestResponse,
  KnowledgeReindexResponse,
  KnowledgeSearchResponse,
  RefundResponse,
  RuntimeAgentListResponse,
  RuntimeCostResponse,
  RuntimeTraceDetailResponse,
  RuntimeTraceListResponse,
  TenantListResponse,
  TenantUsersResponse,
  TicketCreateRequest,
  TicketDetailResponse,
  TicketListResponse,
  TicketPatchRequest,
} from "@/lib/types";

/* ---------- identity ---------- */

export function useTenants() {
  return useQuery({
    queryKey: ["identity", "tenants"],
    queryFn: () => api.get<TenantListResponse>("/api/v1/identity/tenants", { limit: 200 }),
  });
}

export function useTenantUsers(tenantId: string | null) {
  return useQuery({
    queryKey: ["identity", "users", tenantId],
    queryFn: () =>
      api.get<TenantUsersResponse>(`/api/v1/identity/tenants/${tenantId}/users`, { limit: 500 }),
    enabled: Boolean(tenantId),
  });
}

/* ---------- conversations ---------- */

export function useConversations(status?: string) {
  return useQuery({
    queryKey: ["conversations", status ?? "all"],
    queryFn: () => api.get<ConversationListResponse>("/api/v1/conversations", { status, limit: 50 }),
  });
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversations", conversationId],
    queryFn: () => api.get<ConversationDetailResponse>(`/api/v1/conversations/${conversationId}`),
    enabled: Boolean(conversationId),
  });
}

export function useCreateConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ConversationCreateRequest) =>
      api.post<ConversationDetailResponse>("/api/v1/conversations", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }),
  });
}

export function useSendConversationMessage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, body }: { conversationId: string; body: ConversationMessageCreateRequest }) =>
      api.post<ConversationDetailResponse>(`/api/v1/conversations/${conversationId}/messages`, body),
    onSuccess: (_data, variables) =>
      qc.invalidateQueries({ queryKey: ["conversations", variables.conversationId] }),
  });
}

/* ---------- tickets ---------- */

export function useTickets(status?: string) {
  return useQuery({
    queryKey: ["tickets", status ?? "all"],
    queryFn: () => api.get<TicketListResponse>("/api/v1/tickets", { status, limit: 100 }),
  });
}

export function useTicket(ticketId: string | null) {
  return useQuery({
    queryKey: ["tickets", ticketId],
    queryFn: () => api.get<TicketDetailResponse>(`/api/v1/tickets/${ticketId}`),
    enabled: Boolean(ticketId),
  });
}

export function useCreateTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: TicketCreateRequest) => api.post<TicketDetailResponse>("/api/v1/tickets", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tickets"] }),
  });
}

export function useUpdateTicket() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ ticketId, body }: { ticketId: string; body: TicketPatchRequest }) =>
      api.patch<TicketDetailResponse>(`/api/v1/tickets/${ticketId}`, body),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["tickets"] });
      qc.invalidateQueries({ queryKey: ["tickets", variables.ticketId] });
    },
  });
}

/* ---------- approvals ---------- */

export function useApprovals(status?: string) {
  return useQuery({
    queryKey: ["approvals", status ?? "all"],
    queryFn: () => api.get<ApprovalListResponse>("/api/v1/approvals", { status, limit: 100 }),
  });
}

export function useApproval(approvalId: string | null) {
  return useQuery({
    queryKey: ["approvals", approvalId],
    queryFn: () => api.get<ApprovalDetailResponse>(`/api/v1/approvals/${approvalId}`),
    enabled: Boolean(approvalId),
  });
}

export function useActOnApproval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ approvalId, body }: { approvalId: string; body: ApprovalActionRequest }) =>
      api.post<RefundResponse>(`/api/v1/approvals/${approvalId}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["approvals"] });
      qc.invalidateQueries({ queryKey: ["tickets"] });
    },
  });
}

/* ---------- knowledge ---------- */

export function useKnowledgeDocuments() {
  return useQuery({
    queryKey: ["knowledge", "documents"],
    queryFn: () => api.get<KnowledgeDocumentListResponse>("/api/v1/knowledge/documents", { limit: 100 }),
  });
}

export function useKnowledgeSearch(query: string, enabled = false) {
  return useQuery({
    queryKey: ["knowledge", "search", query],
    queryFn: () => api.get<KnowledgeSearchResponse>("/api/v1/knowledge/search", { q: query, limit: 10 }),
    enabled: enabled && query.trim().length > 0,
  });
}

export function useIngestDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: KnowledgeIngestRequest) =>
      api.post<KnowledgeIngestResponse>("/api/v1/knowledge/documents", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge", "documents"] }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      api.del<KnowledgeDeleteResponse>(`/api/v1/knowledge/documents/${documentId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge", "documents"] }),
  });
}

export function useReindexKnowledge() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<KnowledgeReindexResponse>("/api/v1/knowledge/reindex"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["knowledge", "documents"] }),
  });
}

/* ---------- runtime ---------- */

export function useRuntimeTraces() {
  return useQuery({
    queryKey: ["runtime", "traces"],
    queryFn: () => api.get<RuntimeTraceListResponse>("/api/v1/runtime/traces", { limit: 50 }),
  });
}

export function useRuntimeTrace(traceId: string | null) {
  return useQuery({
    queryKey: ["runtime", "traces", traceId],
    queryFn: () => api.get<RuntimeTraceDetailResponse>(`/api/v1/runtime/traces/${traceId}`),
    enabled: Boolean(traceId),
  });
}

export function useRuntimeCosts() {
  return useQuery({
    queryKey: ["runtime", "costs"],
    queryFn: () => api.get<RuntimeCostResponse>("/api/v1/runtime/costs"),
  });
}

export function useRuntimeAgents() {
  return useQuery({
    queryKey: ["runtime", "agents"],
    queryFn: () => api.get<RuntimeAgentListResponse>("/api/v1/runtime/agents"),
  });
}

/* ---------- evaluations ---------- */

export function useEvaluationRuns() {
  return useQuery({
    queryKey: ["evaluations", "runs"],
    queryFn: () => api.get<EvaluationRunListResponse>("/api/v1/evaluations", { limit: 50 }),
  });
}

export function useRunEvaluation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: EvaluationRunRequest) =>
      api.post<EvaluationRunResponse>("/api/v1/evaluations/run", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["evaluations", "runs"] }),
  });
}

/* ---------- auth ---------- */

export function useRequestToken() {
  return useMutation({
    mutationFn: (body: { tenant_id: string; user_id: string; actor_type: "user" | "system" }) =>
      api.post<AuthTokenResponse>("/api/v1/auth/tokens", body),
  });
}

/* ---------- consultation (sync) ---------- */

export function useConsultation() {
  return useMutation({
    mutationFn: (body: { thread_id: string; message: string }) =>
      api.post<CustomerConsultationResponse>("/api/v1/customer-consultations", body),
  });
}
