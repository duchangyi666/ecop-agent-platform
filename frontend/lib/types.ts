/** API types translated from backend Pydantic schemas (backend/api/schemas.py). */

export interface ApiErrorPayload {
  code: string;
  message: string;
  request_id: string;
}

export interface ApiErrorBody {
  error: ApiErrorPayload;
}

/* ---------- identity (dev helper routes) ---------- */

export interface TenantItem {
  id: string;
  slug: string;
  name: string;
  status: string;
}

export interface TenantListResponse {
  request_id: string;
  tenants: TenantItem[];
}

export interface IdentityUserItem {
  id: string;
  email: string;
  display_name: string;
  status: string;
  roles?: string[];
}

export interface TenantUsersResponse {
  request_id: string;
  tenant_id: string;
  users: IdentityUserItem[];
}

/* ---------- auth ---------- */

export interface AuthTokenRequest {
  tenant_id: string;
  user_id: string;
  actor_type: "user" | "system";
}

export interface AuthTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

/* ---------- conversations ---------- */

export interface ConversationItem {
  conversation_id: string;
  customer_id: string | null;
  user_id: string | null;
  channel: string;
  subject: string;
  status: string;
  started_at: string;
  resolved_at: string | null;
  message_count: number;
}

export interface ConversationMessageItem {
  message_id: string;
  author_id: string | null;
  author_type: string;
  role: string;
  body: string;
  visibility: string;
  created_at: string;
}

export interface ConversationListResponse {
  request_id: string;
  conversations: ConversationItem[];
}

export interface ConversationDetailResponse {
  request_id: string;
  conversation: ConversationItem;
  messages: ConversationMessageItem[];
}

export interface ConversationCreateRequest {
  customer_id?: string | null;
  user_id?: string | null;
  channel?: string;
  subject: string;
  initial_message?: string | null;
}

export interface ConversationMessageCreateRequest {
  role?: "user" | "agent" | "system";
  body: string;
  visibility?: "public" | "internal";
}

/* ---------- tickets ---------- */

export interface TicketListItem {
  ticket_id: string;
  customer_id: string;
  subject: string;
  category: string | null;
  priority: string;
  status: string;
  current_assignee_id: string | null;
  resolved_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TicketListResponse {
  request_id: string;
  tickets: TicketListItem[];
}

export interface TicketMessageItem {
  message_id: string;
  author_id: string | null;
  body: string;
  visibility: string;
  created_at: string;
}

export interface TicketEventItem {
  event_id: string;
  actor_id: string | null;
  event_type: string;
  from_status: string | null;
  to_status: string | null;
  payload_summary: Record<string, unknown>;
  occurred_at: string;
}

export interface TicketDetailResponse {
  request_id: string;
  ticket: TicketListItem;
  messages: TicketMessageItem[];
  events: TicketEventItem[];
}

export interface TicketCreateRequest {
  thread_id: string;
  customer_id: string;
  subject: string;
  priority: "low" | "medium" | "high" | "urgent";
  description_summary?: string | null;
  message?: string | null;
}

export interface TicketPatchRequest {
  status?: string;
  subject?: string;
  description_summary?: string;
  priority?: "low" | "medium" | "high" | "urgent";
  note?: string;
}

/* ---------- approvals ---------- */

export interface ApprovalItem {
  approval_request_id: string;
  ticket_id: string | null;
  refund_id: string | null;
  action: string;
  amount: string | null;
  risk_level: string;
  approval_role: string;
  status: string;
  expires_at: string;
  checkpoint_reference: string | null;
  action_count: number;
}

export interface ApprovalListResponse {
  request_id: string;
  approvals: ApprovalItem[];
}

export interface ApprovalActionItem {
  action_id: string;
  actor_id: string | null;
  action: string;
  reason: string;
  changes_summary: Record<string, unknown>;
  acted_at: string;
}

export interface ApprovalDetailResponse {
  request_id: string;
  approval: ApprovalItem;
  actions: ApprovalActionItem[];
}

export interface ApprovalActionRequest {
  thread_id: string;
  approved: boolean;
  reason: string;
}

/* ---------- knowledge ---------- */

export interface KnowledgeDocumentListItem {
  document_id: string;
  external_document_id: string;
  title: string;
  status: string;
  source_uri: string | null;
  visibility: string;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeDocumentListResponse {
  request_id: string;
  documents: KnowledgeDocumentListItem[];
}

export interface KnowledgeDocumentResponse {
  document_id: string;
  title: string;
  external_document_id: string;
  source_uri: string | null;
  status: string;
  visibility: string;
  content_snippet: string | null;
  score: number | null;
}

export interface KnowledgeSearchResponse {
  request_id: string;
  thread_id: string;
  status: string;
  next_action: string | null;
  final_response: string | null;
  results: KnowledgeDocumentResponse[];
  trace_id: string | null;
}

export interface KnowledgeIngestRequest {
  thread_id: string;
  external_document_id: string;
  title: string;
  source_uri?: string | null;
  visibility?: "tenant" | "public";
  content: string;
  chunk_size?: number;
  chunk_overlap?: number;
}

export interface KnowledgeIngestResponse {
  request_id: string;
  thread_id: string;
  document_id: string;
  version_number: number;
  chunk_count: number;
  vector_indexed: boolean;
  trace_id: string | null;
}

export interface KnowledgeDeleteResponse {
  request_id: string;
  document_id: string;
  status: string;
  vector_indexed: boolean;
}

export interface KnowledgeReindexResponse {
  request_id: string;
  document_count: number;
  chunk_count: number;
  vector_indexed: boolean;
}

/* ---------- customer consultation ---------- */

export interface ChatHistoryItem {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface CustomerConsultationRequest {
  thread_id: string;
  message: string;
  /** Legacy field; the consultation service loads history from the server. */
  history?: ChatHistoryItem[];
}

export interface CustomerConsultationResponse {
  request_id: string;
  thread_id: string;
  status: string;
  next_action: string | null;
  final_response: string | null;
  knowledge_evidence_count: number;
  memory_candidate_count: number;
  trace_id: string | null;
}

/* ---------- refunds ---------- */

export interface RefundCreateRequest {
  thread_id: string;
  payment_id: string;
  amount: string;
  refund_idempotency_key: string;
  message: string;
}

export interface RefundResponse {
  request_id: string;
  thread_id: string;
  status: string;
  refund_id: string | null;
  approval_request_id: string | null;
  trace_id: string | null;
  next_action: string | null;
  reason: string | null;
}

export interface WorkflowStatusResponse {
  request_id: string;
  thread_id: string;
  status: string;
  next_action: string | null;
  refund_id: string | null;
  approval_request_id: string | null;
  trace_id: string | null;
  has_refund_idempotency_key: boolean;
}

/* ---------- runtime ---------- */

export interface RuntimeTraceItem {
  trace_id: string;
  trace_key: string;
  status: string;
  entrypoint: string;
  started_at: string;
  finished_at: string | null;
  total_cost: string;
  error_summary: string | null;
}

export interface RuntimeTraceListResponse {
  request_id: string;
  traces: RuntimeTraceItem[];
}

export interface RuntimeSpanItem {
  span_id: string;
  node_name: string;
  status: string;
  input_summary: string;
  output_summary: string;
  started_at: string;
  duration_ms: number | null;
}

export interface RuntimeTraceDetailResponse {
  request_id: string;
  trace: RuntimeTraceItem;
  spans: RuntimeSpanItem[];
}

export interface RuntimeCostResponse {
  request_id: string;
  trace_count: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost: string;
  failed_count: number;
}

export interface RuntimeAgentItem {
  agent_id: string;
  agent_code: string;
  name: string;
  status: string;
}

export interface RuntimeAgentListResponse {
  request_id: string;
  agents: RuntimeAgentItem[];
}

/* ---------- evaluations ---------- */

export interface EvaluationRunItem {
  run_id: string;
  dataset_id: string;
  status: string;
  metrics: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
}

export interface EvaluationRunListResponse {
  request_id: string;
  runs: EvaluationRunItem[];
}

export interface EvaluationRunRequest {
  dataset_code: string;
  limit: number;
}

export interface EvaluationRunResponse {
  request_id: string;
  run_id: string;
  dataset_code: string;
  case_count: number;
  metrics: Record<string, unknown>;
  status: string;
}

/* ---------- health ---------- */

export interface HealthResponse {
  status: string;
}
