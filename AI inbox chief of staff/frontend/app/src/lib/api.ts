const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("session_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body);
  }

  return res.json();
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: string;
  service: string;
  version: string;
}

export type UserRole = "user" | "admin";

export interface CurrentUser {
  id: string;
  email: string;
  display_name: string | null;
  role: UserRole;
  is_active: boolean;
}

export interface AdminUserSummary {
  id: string;
  email: string;
  display_name: string | null;
  role: UserRole;
  is_active: boolean;
  mailbox_count: number;
  created_at: string;
}

export interface AdminUserListResponse {
  users: AdminUserSummary[];
  total: number;
}

export interface AdminActivityStats {
  total_users: number;
  active_users_in_window: number;
  total_mailboxes: number;
  triage_decisions: number;
  drafts_generated: number;
  mutations_applied: number;
  undos_performed: number;
  corrections_submitted: number;
  critical_audit_events: number;
  window_days: number;
}

export interface ConnectResponse {
  authorization_url: string;
  state: string;
}

export interface AuthSessionResponse {
  session_token: string;
  user: CurrentUser;
}

export interface CallbackResponse {
  mailbox_id: string;
  gmail_email: string;
  connected: boolean;
}

export interface DisconnectResponse {
  mailbox_id: string;
  disconnected: boolean;
}

export interface MailboxSummary {
  id: string;
  gmail_email: string;
  is_connected: boolean;
  is_active: boolean;
  brief_enabled: boolean;
  draft_enabled: boolean;
  auto_archive_enabled: boolean;
  brief_morning_hour: number | null;
  brief_afternoon_hour: number | null;
  activation_mode: "shadow" | "observe" | "auto";
  gmail_watch_expiration: string | null;
}

export interface UpdateMailboxSettings {
  brief_enabled?: boolean;
  draft_enabled?: boolean;
  auto_archive_enabled?: boolean;
  brief_morning_hour?: number;
  brief_afternoon_hour?: number;
  activation_mode?: "shadow" | "observe" | "auto";
}

export interface InstructionRequest {
  instruction: string;
  mailbox_id?: string | null;
  conversation_id?: string | null;
}

export interface InstructionResponse {
  accepted: boolean;
  rules_created: number;
  feedback_event_id: string;
  message: string;
  needs_clarification: boolean;
  clarification_question: string | null;
  conversation_id: string;
  user_message_id: string;
  assistant_message_id: string;
}

export type MemoryScope = "mailbox_specific" | "user_global";
export type MemoryTypeValue = "profile" | "policy" | "style" | "sender";

export interface Memory {
  id: string;
  user_id: string;
  mailbox_id: string | null;
  scope: MemoryScope;
  applies_to_all_mailboxes: boolean;
  memory_type: MemoryTypeValue;
  content: string;
  structured_data: Record<string, unknown>;
  source: string;
  confidence: number;
  is_active: boolean;
  last_reinforced_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MemoryListResponse {
  memories: Memory[];
  total: number;
}

export interface MemoryUpdate {
  content?: string;
  is_active?: boolean;
  confidence?: number;
}

export interface MemoryCreate {
  mailbox_id?: string | null;
  scope?: MemoryScope;
  memory_type: MemoryTypeValue;
  content: string;
  structured_data?: Record<string, unknown>;
  source?: string;
  confidence?: number;
  applies_to_all_mailboxes?: boolean;
}

export interface ConversationSummary {
  id: string;
  title: string;
  mailbox_id: string | null;
  message_count: number;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
  last_message_preview: string | null;
}

export interface ConversationListResponse {
  conversations: ConversationSummary[];
  total: number;
}

export interface AssistantMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response_data: {
    rules_created?: number;
    needs_clarification?: boolean;
    clarification_question?: string | null;
    feedback_event_id?: string;
    accepted?: boolean;
  };
  feedback_event_id: string | null;
  created_at: string;
}

export interface AssistantSuggestion {
  id: string;
  kind: string;
  headline: string;
  rationale: string;
  instruction_text: string;
  evidence_count: number;
  mailbox_id: string | null;
}

export interface AssistantSuggestionsResponse {
  suggestions: AssistantSuggestion[];
  window_days: number;
}

export interface ConversationDetail {
  id: string;
  title: string;
  mailbox_id: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
  messages: AssistantMessage[];
}

export interface UndoRequest {
  undo_token: string;
}

export interface UndoResponse {
  ledger_id: string;
  reversed: boolean;
  message: string;
}

export interface TriageCorrectionRequest {
  email_id: string;
  correct_outcome: string;
  reason?: string;
}

export interface TriageCorrectionResponse {
  correction_id: string;
  memory_updated: boolean;
  message: string;
}

export interface DraftFeedbackRequest {
  draft_id: string;
  action: "accepted" | "edited" | "discarded";
  edited_text?: string;
}

export interface DataExportResponse {
  user_id: string;
  exported_at: string;
  data: {
    user: { id: string; email: string; display_name: string };
    mailboxes: Array<{
      id: string;
      gmail_email: string;
      is_active: boolean;
      created_at: string | null;
    }>;
    memories: Array<{
      id: string;
      memory_type: string;
      content: string;
      scope: string;
      confidence: number;
      created_at: string | null;
    }>;
    feedback: Array<{
      id: string;
      feedback_type: string;
      raw_content: string;
      created_at: string | null;
    }>;
    email_metadata: Array<{
      id: string;
      from_address: string;
      subject: string;
      received_at: string | null;
    }>;
  };
}

export interface DataDeletionResponse {
  user_id: string;
  deleted: boolean;
  details: { tokens_revoked: number };
}

export interface ActivityStats {
  emails_triaged: number;
  drafts_generated: number;
  mutations_applied: number;
  undos_performed: number;
  window_days: number;
}

export interface ActivityEvent {
  id: string;
  event_type: string;
  actor: string;
  resource_type: string | null;
  resource_id: string | null;
  severity: string;
  mailbox_id: string | null;
  created_at: string;
  payload: Record<string, unknown>;
}

export interface ActivityEventsResponse {
  events: ActivityEvent[];
  total: number;
}

export type TimelineKind = "triage" | "mutation" | "draft" | "audit";

export interface TimelineItem {
  id: string;
  kind: TimelineKind;
  timestamp: string;
  headline: string;
  detail: string | null;
  related_email_id: string | null;
  related_email_subject: string | null;
  related_email_from: string | null;
  extra: Record<string, unknown>;
}

export interface TimelineResponse {
  items: TimelineItem[];
  mailbox_id: string;
  next_before: string | null;
  has_more: boolean;
}

export interface MutationSummary {
  id: string;
  mailbox_id: string;
  mutation_type: string;
  status: "pending" | "applied" | "undone" | "undo_failed" | "expired";
  email_subject: string | null;
  email_from: string | null;
  reason_trace: string;
  undo_token: string;
  undo_expires_at: string;
  created_at: string;
}

export interface MutationListResponse {
  mutations: MutationSummary[];
  total: number;
}

export type TriageOutcome =
  | "inbox_keep"
  | "brief_only"
  | "draft_candidate"
  | "manual_review"
  | "protected";

export interface TriageDecisionSummary {
  id: string;
  email_id: string;
  mailbox_id: string;
  email_subject: string | null;
  email_from: string | null;
  outcome: TriageOutcome;
  confidence: number;
  method: string;
  rule_matched: string | null;
  corrected_by_user: boolean;
  created_at: string;
}

export interface TriageDecisionListResponse {
  decisions: TriageDecisionSummary[];
  total: number;
}

export interface BriefItem {
  id: string;
  category: string | null;
  summary: string | null;
  key_points: string[] | null;
  gmail_open_url: string | null;
  importance_score: number | null;
  sort_order: number | null;
}

export interface Brief {
  id: string;
  mailbox_id: string;
  window: string;
  status: string;
  subject_line: string | null;
  item_count: number | null;
  scheduled_at: string | null;
  delivered_at: string | null;
  created_at: string | null;
  items: BriefItem[];
}

export interface BriefListResponse {
  briefs: Brief[];
  total: number;
}

export type ExperimentStatus = "draft" | "active" | "paused" | "completed";
export type ExperimentMetric =
  | "triage_correction_rate"
  | "draft_acceptance_rate"
  | "avg_confidence";

export interface ExperimentVariantOut {
  id: string;
  label: string;
  prompt_version: string;
  traffic_pct: number;
  is_control: boolean;
}

export interface ExperimentOut {
  id: string;
  name: string;
  description: string | null;
  prompt_name: string;
  primary_metric: ExperimentMetric;
  status: ExperimentStatus;
  started_at: string | null;
  stopped_at: string | null;
  created_at: string;
  updated_at: string;
  variants: ExperimentVariantOut[];
}

export interface ExperimentListResponse {
  experiments: ExperimentOut[];
  total: number;
}

export interface VariantCreate {
  label: string;
  prompt_version: string;
  traffic_pct: number;
  is_control: boolean;
}

export interface ExperimentCreate {
  name: string;
  description?: string | null;
  prompt_name: string;
  primary_metric: ExperimentMetric;
  variants: VariantCreate[];
}

export interface VariantStats {
  variant_id: string;
  label: string;
  prompt_version: string;
  is_control: boolean;
  traffic_pct: number;
  sample_size: number;
  metric_value: number | null;
  correction_count: number | null;
  acceptance_count: number | null;
  avg_confidence: number | null;
  z_score_vs_control: number | null;
  p_value_vs_control: number | null;
  is_significant: boolean;
}

export interface ExperimentRollup {
  experiment_id: string;
  primary_metric: ExperimentMetric;
  window_start: string | null;
  window_end: string;
  variants: VariantStats[];
  winner_variant_id: string | null;
  notes: string[];
}

export interface RegistryPrompt {
  name: string;
  active_version: string | null;
  versions: string[];
}

export type SLOStatus = "pass" | "warn" | "fail" | "not_measured";
export type SLOCategory = "quality" | "latency" | "undo" | "reliability" | "cost";

export interface SLOMetric {
  id: string;
  name: string;
  category: SLOCategory;
  target_value: number;
  operator: "<=" | ">=";
  unit: string;
  description: string;
  value: number | null;
  sample_size: number;
  status: SLOStatus;
  note: string | null;
}

export interface SLOStatusResponse {
  window_days: number;
  metrics: SLOMetric[];
  summary: Record<SLOStatus, number>;
  launch_ready: boolean;
}

// ── API Functions ───────────────────────────────────────────────────────────

export const api = {
  health: {
    check: () => request<HealthResponse>("/health/"),
    ready: () => request<{ status: string; checks: Record<string, string> }>("/health/ready"),
  },

  auth: {
    me: () => request<CurrentUser>("/auth/me"),
    register: (payload: { email: string; password: string; display_name?: string }) =>
      request<AuthSessionResponse>("/auth/register", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    login: (payload: { email: string; password: string }) =>
      request<AuthSessionResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    logout: () => request<{ logged_out: boolean }>("/auth/logout", { method: "POST" }),
  },

  mailboxConnect: {
    connect: () => request<ConnectResponse>("/mailbox-connect/gmail/connect"),
    callback: (code: string, state: string) =>
      request<CallbackResponse>(`/mailbox-connect/gmail/callback?code=${encodeURIComponent(code)}&state=${encodeURIComponent(state)}`),
    disconnect: (mailboxId: string) =>
      request<DisconnectResponse>(`/mailbox-connect/gmail/disconnect/${mailboxId}`, { method: "POST" }),
  },

  admin: {
    listUsers: (params: { limit?: number; offset?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<AdminUserListResponse>(`/admin/users${q ? `?${q}` : ""}`);
    },
    activityStats: (params: { window_days?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.window_days) qs.set("window_days", String(params.window_days));
      const q = qs.toString();
      return request<AdminActivityStats>(`/admin/activity-stats${q ? `?${q}` : ""}`);
    },
    setRole: (userId: string, role: UserRole) =>
      request<{ id: string; role: UserRole }>(`/admin/users/${userId}/role`, {
        method: "PATCH",
        body: JSON.stringify({ role }),
      }),
  },

  mailboxes: {
    list: () => request<MailboxSummary[]>("/mailboxes/"),
    get: (id: string) => request<MailboxSummary>(`/mailboxes/${id}`),
    updateSettings: (id: string, settings: UpdateMailboxSettings) =>
      request<{ updated: boolean }>(`/mailboxes/${id}/settings`, {
        method: "PATCH",
        body: JSON.stringify(settings),
      }),
  },

  assistant: {
    instruct: (req: InstructionRequest) =>
      request<InstructionResponse>("/assistant/instruction", {
        method: "POST",
        body: JSON.stringify(req),
      }),
    listConversations: (params: { mailbox_id?: string; limit?: number; offset?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<ConversationListResponse>(
        `/assistant/conversations${q ? `?${q}` : ""}`,
      );
    },
    getConversation: (id: string) =>
      request<ConversationDetail>(`/assistant/conversations/${id}`),
    deleteConversation: (id: string) =>
      request<{ deleted: boolean; conversation_id: string }>(
        `/assistant/conversations/${id}`,
        { method: "DELETE" },
      ),
    suggestions: (params: { mailbox_id?: string; window_days?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.window_days) qs.set("window_days", String(params.window_days));
      const q = qs.toString();
      return request<AssistantSuggestionsResponse>(
        `/assistant/suggestions${q ? `?${q}` : ""}`,
      );
    },
  },

  memories: {
    list: (params: {
      mailbox_id?: string;
      scope?: MemoryScope;
      memory_type?: MemoryTypeValue;
      is_active?: boolean;
      limit?: number;
      offset?: number;
    } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.scope) qs.set("scope", params.scope);
      if (params.memory_type) qs.set("memory_type", params.memory_type);
      if (params.is_active !== undefined) qs.set("is_active", String(params.is_active));
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<MemoryListResponse>(`/memories/${q ? `?${q}` : ""}`);
    },
    create: (payload: MemoryCreate) =>
      request<Memory>("/memories/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (id: string, update: MemoryUpdate) =>
      request<Memory>(`/memories/${id}`, {
        method: "PATCH",
        body: JSON.stringify(update),
      }),
    delete: (id: string) =>
      request<{ deleted: boolean; memory_id: string }>(`/memories/${id}`, {
        method: "DELETE",
      }),
  },

  undo: {
    mutation: (req: UndoRequest) =>
      request<UndoResponse>("/undo/mutation", {
        method: "POST",
        body: JSON.stringify(req),
      }),
    listMutations: (params: {
      mailbox_id?: string;
      status?: string;
      limit?: number;
      offset?: number;
    } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.status) qs.set("status", params.status);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<MutationListResponse>(`/undo/mutations${q ? `?${q}` : ""}`);
    },
  },

  feedback: {
    triageCorrection: (req: TriageCorrectionRequest) =>
      request<TriageCorrectionResponse>("/feedback/triage-correction", {
        method: "POST",
        body: JSON.stringify(req),
      }),
    draftFeedback: (req: DraftFeedbackRequest) =>
      request<{ updated: boolean; draft_id: string; status: string }>("/feedback/draft-feedback", {
        method: "POST",
        body: JSON.stringify(req),
      }),
    listTriageDecisions: (params: {
      mailbox_id?: string;
      outcome?: string;
      limit?: number;
      offset?: number;
    } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.outcome) qs.set("outcome", params.outcome);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<TriageDecisionListResponse>(
        `/feedback/triage-decisions${q ? `?${q}` : ""}`,
      );
    },
  },

  activity: {
    stats: (params: { mailbox_id?: string; window_days?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.window_days) qs.set("window_days", String(params.window_days));
      const q = qs.toString();
      return request<ActivityStats>(`/activity/stats${q ? `?${q}` : ""}`);
    },
    events: (params: {
      mailbox_id?: string;
      event_type_prefix?: string;
      limit?: number;
      offset?: number;
    } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.event_type_prefix) qs.set("event_type_prefix", params.event_type_prefix);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<ActivityEventsResponse>(`/activity/events${q ? `?${q}` : ""}`);
    },
    timeline: (params: {
      mailbox_id: string;
      limit?: number;
      before?: string;
      kinds?: TimelineKind[];
    }) => {
      const qs = new URLSearchParams();
      qs.set("mailbox_id", params.mailbox_id);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.before) qs.set("before", params.before);
      if (params.kinds && params.kinds.length > 0)
        qs.set("kinds", params.kinds.join(","));
      return request<TimelineResponse>(`/activity/timeline?${qs.toString()}`);
    },
  },

  briefs: {
    list: (params: { mailbox_id?: string; limit?: number; offset?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.mailbox_id) qs.set("mailbox_id", params.mailbox_id);
      if (params.limit) qs.set("limit", String(params.limit));
      if (params.offset) qs.set("offset", String(params.offset));
      const q = qs.toString();
      return request<BriefListResponse>(`/briefs/${q ? `?${q}` : ""}`);
    },
    get: (id: string) => request<Brief>(`/briefs/${id}`),
  },

  experiments: {
    list: (params: { status?: ExperimentStatus; prompt_name?: string } = {}) => {
      const qs = new URLSearchParams();
      if (params.status) qs.set("status", params.status);
      if (params.prompt_name) qs.set("prompt_name", params.prompt_name);
      const q = qs.toString();
      return request<ExperimentListResponse>(`/experiments/${q ? `?${q}` : ""}`);
    },
    get: (id: string) => request<ExperimentOut>(`/experiments/${id}`),
    create: (payload: ExperimentCreate) =>
      request<ExperimentOut>("/experiments/", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    update: (id: string, update: { status?: ExperimentStatus; name?: string; description?: string }) =>
      request<ExperimentOut>(`/experiments/${id}`, {
        method: "PATCH",
        body: JSON.stringify(update),
      }),
    delete: (id: string) =>
      request<{ deleted: boolean; experiment_id: string }>(`/experiments/${id}`, {
        method: "DELETE",
      }),
    results: (id: string) =>
      request<ExperimentRollup>(`/experiments/${id}/results`),
    registryPrompts: () =>
      request<RegistryPrompt[]>("/experiments/registry/prompts"),
  },

  slo: {
    status: (params: { window_days?: number } = {}) => {
      const qs = new URLSearchParams();
      if (params.window_days) qs.set("window_days", String(params.window_days));
      const q = qs.toString();
      return request<SLOStatusResponse>(`/slo/status${q ? `?${q}` : ""}`);
    },
  },

  data: {
    export: () => request<DataExportResponse>("/data/export"),
    deleteAccount: () => request<DataDeletionResponse>("/data/delete-account", { method: "DELETE" }),
  },
};

export { ApiError };
