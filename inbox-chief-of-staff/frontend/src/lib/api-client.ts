import type { PaginatedResponse, Message, Draft, Brief, Priority, DraftStatus, User } from "@/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text);
  }
  return response.json() as Promise<T>;
}

export const api = {
  messages: {
    list: (params?: { priority?: string; page?: number }) => {
      const qs = new URLSearchParams();
      if (params?.priority) qs.set("priority", params.priority);
      if (params?.page) qs.set("page", String(params.page));
      return request<PaginatedResponse<Message>>(`/messages?${qs}`);
    },
    get: (id: string) => request<Message>(`/messages/${id}`),
    overrideTriage: (id: string, priority: Priority) =>
      request(`/messages/${id}/triage-override`, {
        method: "POST",
        body: JSON.stringify({ priority }),
      }),
  },
  drafts: {
    list: () => request<PaginatedResponse<Draft>>("/drafts"),
    get: (id: string) => request<Draft>(`/drafts/${id}`),
    update: (id: string, body: { status?: DraftStatus; body?: string }) =>
      request<Draft>(`/drafts/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      }),
  },
  briefs: {
    list: () => request<PaginatedResponse<Brief>>("/briefs"),
    get: (id: string) => request<Brief>(`/briefs/${id}`),
  },
  feedback: {
    triage: (messageId: string, correctedPriority: Priority) =>
      request("/feedback/triage", {
        method: "POST",
        body: JSON.stringify({
          message_id: messageId,
          corrected_priority: correctedPriority,
        }),
      }),
    draft: (
      draftId: string,
      rating: "helpful" | "unhelpful",
      notes?: string,
    ) =>
      request("/feedback/draft", {
        method: "POST",
        body: JSON.stringify({ draft_id: draftId, rating, notes }),
      }),
  },
  auth: {
    me: () => request<User>("/auth/me"),
    logout: () => request("/auth/logout", { method: "DELETE" }),
  },
};
