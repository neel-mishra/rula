export type Priority = "urgent" | "normal" | "brief" | "archive";
export type DraftStatus = "pending" | "accepted" | "rejected" | "edited";
export type TimeWindow = "morning" | "afternoon";
export type WorkflowState =
  | "ingested"
  | "normalized"
  | "triaged"
  | "draft_queued"
  | "brief_queued"
  | "pending_review"
  | "completed"
  | "rejected";

export interface User {
  id: string;
  email: string;
  timezone: string;
}

export interface TriageResult {
  id: string;
  priority: Priority;
  confidence: number;
  rationale: string;
  labels: string[];
  modelVersion: string;
  createdAt: string;
}

export interface Message {
  id: string;
  gmailMessageId: string;
  gmailThreadId: string;
  subject: string;
  senderEmail: string;
  senderName: string;
  receivedAt: string;
  bodyPreview: string;
  body?: string;
  hasDraft?: boolean;
  triage: TriageResult | null;
  workflowState: WorkflowState;
}

export interface Draft {
  id: string;
  workflowRunId: string;
  body: string;
  subjectLine: string;
  confidence: number;
  status: DraftStatus;
  userFeedback: string | null;
  createdAt: string;
  reviewedAt: string | null;
  originalMessage?: Message;
}

export interface ActionItem {
  text: string;
  messageId?: string;
  from?: string;
  due?: string;
  done?: boolean;
}

export interface BriefThread {
  id: string;
  sender: string;
  subject: string;
  snippet: string;
  timestamp: string;
  read: boolean;
}

export interface Brief {
  id: string;
  timeWindow: TimeWindow;
  summaryMarkdown: string;
  actionItems: ActionItem[];
  messageIds: string[];
  createdAt: string;
  threadCount?: number;
  generatedAt?: string;
  modelVersion?: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
  hasMore: boolean;
}
