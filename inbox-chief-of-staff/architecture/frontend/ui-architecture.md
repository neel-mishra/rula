# Frontend UI Architecture

**Project:** Inbox Chief of Staff  
**Phase:** Prototype  
**Last updated:** 2026-04-30

---

## Stack

| Layer | Technology | Notes |
|---|---|---|
| Framework | Next.js 14 (App Router) | Server components by default; client components only where interactivity is required |
| Language | TypeScript (strict mode) | `tsconfig.json` targets ES2022, `noUncheckedIndexedAccess: true` |
| Styling | Tailwind CSS + shadcn/ui | shadcn components copied into `components/ui/` — not a runtime dependency |
| Server state | TanStack Query (React Query v5) | Caching, polling, optimistic updates |
| Client state | Zustand | UI state only (selection, modals, filter tabs) |
| Auth | httpOnly cookie session (JWT) | No tokens in localStorage or JS-accessible cookies |
| Hosting | Vercel | Preview per PR; production from `main` |

---

## App Route Structure

```
app/
├── page.tsx                         → redirect: authed → /inbox, unauthed → /login
│
├── (auth)/
│   ├── login/
│   │   └── page.tsx                 → Google OAuth sign-in screen
│   └── callback/
│       └── route.ts                 → OAuth code exchange, session cookie set
│
├── (app)/
│   ├── layout.tsx                   → authenticated shell: top nav, session guard
│   ├── inbox/
│   │   └── page.tsx                 → priority triage feed (default view)
│   ├── drafts/
│   │   └── page.tsx                 → draft review queue
│   ├── brief/
│   │   └── page.tsx                 → brief reader (morning / afternoon)
│   └── settings/
│       ├── page.tsx                 → mailbox settings, preferences, feedback history
│       └── policy/
│           └── page.tsx             → action policy view (read-only in Prototype)
│
└── api/
    ├── auth/
    │   └── [...nextauth]/route.ts   → session management endpoints
    └── health/
        └── route.ts                 → liveness probe for Vercel
```

**Route conventions:**
- `(auth)` group: no session guard, no app shell.
- `(app)` group: session guard in `layout.tsx` redirects to `/login` if cookie missing or expired.
- All data fetching against the backend happens client-side via React Query (no `fetch` in Server Components for mutable data, to preserve cache control at the query layer).

---

## Component Boundaries

### TriageFeed

**Location:** `components/triage/TriageFeed.tsx`  
**Rendered in:** `/inbox`  
**Type:** Client component

Responsibilities:
- Fetches paginated messages with triage results from `GET /messages?priority=<tab>&page=<n>`.
- Polls every 60 seconds (`refetchInterval: 60_000`).
- Renders priority filter tabs: Urgent / Normal / Brief / Archive.
- Tab state lives in Zustand (`useInboxStore.activeTab`).
- Renders a list of `MessageCard` components.
- Handles empty states per tab ("No urgent messages").

Props: none (reads Zustand for active tab, React Query for data).

```
TriageFeed
├── PriorityTabBar           (tab selection — Zustand write)
├── MessageCard[]            (list, virtualized for > 50 items)
└── InboxEmptyState          (conditional)
```

---

### MessageCard

**Location:** `components/triage/MessageCard.tsx`  
**Type:** Client component

Displays per message:
- Sender name + address
- Subject line
- 1-line snippet (truncated)
- `PriorityBadge` (URGENT / NORMAL / BRIEF / ARCHIVE) with color coding
- Confidence indicator (percentage, shown as small text below badge)
- Rationale tooltip (hover/tap activates `Tooltip` from shadcn): full rationale string from API
- `[Approve triage]` button → `PATCH /messages/{id}/triage { approved: true }` with optimistic update
- `[Override]` button → opens `OverridePanel` inline (not a route change)
- Click on card body → sets `useInboxStore.selectedMessageId`, opens `MessageDetailPane`

Props:
```ts
interface MessageCardProps {
  message: TriagedMessage;
}
```

Key behaviors:
- Optimistic update on approve: badge becomes solid immediately, reverts on API error.
- Override panel is inline (rendered inside the card's DOM subtree, not a portal) to keep focus management simple.

---

### MessageDetailPane

**Location:** `components/triage/MessageDetailPane.tsx`  
**Type:** Client component

Opens as a right-side panel (desktop) or full-screen overlay (mobile) when a card is selected.

Displays:
- Full email body (sanitized HTML via DOMPurify)
- AI rationale block (always expanded, never collapsed)
- Priority badge with confidence score
- `[Approve triage]`, `[Override]`, `[Open in Gmail ↗]` buttons
- If a draft exists: callout banner linking to `/drafts`

State: reads `useInboxStore.selectedMessageId`, fetches `GET /messages/{id}` (cached by React Query).

---

### DraftQueue

**Location:** `components/drafts/DraftQueue.tsx`  
**Rendered in:** `/drafts`  
**Type:** Client component

Responsibilities:
- Fetches pending drafts from `GET /drafts?status=pending`.
- Renders filter tabs: All / Pending review / Approved / Rejected.
- Renders a list of `DraftCard` components.
- Tab state lives in Zustand (`useDraftsStore.activeFilter`).

```
DraftQueue
├── DraftFilterTabBar
├── DraftCard[]
└── DraftsEmptyState
```

---

### DraftCard

**Location:** `components/drafts/DraftCard.tsx`  
**Type:** Client component

Displays:
- Original message context (collapsed by default, `<Collapsible>` from shadcn — expandable)
- AI draft body in an edit-in-place `<textarea>` (read-only until user clicks to activate)
- AI rationale strip
- Action buttons:
  - `[Approve → Save to Gmail Drafts]` → `POST /drafts/{id}/approve`
  - `[Edit then Approve]` → activates textarea; `[Save & Approve]` replaces this button
  - `[Reject draft]` → `POST /drafts/{id}/reject { reason }`

Props:
```ts
interface DraftCardProps {
  draft: DraftWithContext;
}
```

Key behaviors:
- No content is written to Gmail Drafts until explicit approval.
- Edited vs. unedited approval is tracked via a local `wasEdited` boolean sent in the approve request body.
- Optimistic update: card moves to Approved/Rejected filter tab immediately; reverts on error.

---

### BriefReader

**Location:** `components/brief/BriefReader.tsx`  
**Rendered in:** `/brief`  
**Type:** Client component

Responsibilities:
- Fetches latest brief for the current time window from `GET /briefs/current`.
- Displays loading skeleton while brief is generating.
- Renders three sections: Summary, Action Items, Thread Digest.
- "Mark read" per item: `PATCH /messages/{id}/brief-read { read: true }`.
- "Mark entire brief as read": batch `PATCH /briefs/{id}/mark-read`.

```
BriefReader
├── BriefHeader              (date, time window, AI rationale strip)
├── BriefSummarySection      (plain-text summary)
├── ActionItemChecklist      (extracted tasks with source links)
└── ThreadDigestList
    └── ThreadDigestItem[]   (snippet + mark-read + open-original per item)
```

---

### FeedbackModal

**Location:** `components/shared/FeedbackModal.tsx`  
**Type:** Client component

Triggered from: any `MessageCard` or `MessageDetailPane` via "Wrong priority?" link.

Displays:
- Current priority with rationale
- Priority radio selector (Urgent / Normal / Brief / Archive)
- Optional free-text reason field (280 char max)
- `[Save correction]` and `[Cancel]`

On save: `POST /feedback { message_id, original_priority, corrected_priority, reason }`.

Modal open/close state lives in Zustand (`useInboxStore.feedbackModalMessageId`).

---

## Data Fetching Strategy

### Transport

All data fetching goes through the REST API at `NEXT_PUBLIC_API_BASE_URL`. No direct database access from the frontend. No GraphQL in Prototype.

### React Query configuration

```ts
// lib/query-client.ts
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,       // 30s before background refetch
      gcTime: 5 * 60_000,      // 5 min cache retention
      retry: 2,
      refetchOnWindowFocus: true,
    },
  },
});
```

### Query key conventions

```
['messages', { priority, page }]   → TriageFeed
['messages', id]                   → MessageDetailPane
['drafts', { status }]             → DraftQueue
['drafts', id]                     → DraftCard
['briefs', 'current']              → BriefReader
['briefs', date]                   → historical brief
['feedback', userId]               → feedback history in settings
```

### Polling

- Inbox (`TriageFeed`): `refetchInterval: 60_000` — polls for new triaged messages.
- All other queries: no automatic polling; refetch on window focus.

### Optimistic updates

Pattern used for approve/reject/override mutations:

```ts
useMutation({
  mutationFn: approveMessage,
  onMutate: async ({ messageId }) => {
    await queryClient.cancelQueries({ queryKey: ['messages'] });
    const snapshot = queryClient.getQueryData(['messages', ...]);
    queryClient.setQueryData(['messages', ...], (old) => applyOptimisticApprove(old, messageId));
    return { snapshot };
  },
  onError: (_err, _vars, context) => {
    queryClient.setQueryData(['messages', ...], context.snapshot);
    toast.error('Action failed. Please try again.');
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: ['messages'] });
  },
});
```

### Auth

- Session is an httpOnly cookie set by the `/api/auth/` route handlers.
- React Query `['session']` query fetches `GET /api/auth/session` to hydrate auth state.
- All API requests include `credentials: 'include'` so the cookie is sent automatically.
- No access token, refresh token, or user ID is stored in JS-accessible storage.
- On 401 from the backend API: React Query `onError` global handler redirects to `/login`.

---

## State Management Split

| State | Owner | Examples |
|---|---|---|
| Server state (messages, drafts, briefs, session) | React Query | Message list, draft bodies, brief content, auth user object |
| UI state (selection, tabs, modals) | Zustand | `selectedMessageId`, `activeTab`, `feedbackModalMessageId`, draft edit mode |
| Form state | React local state / React Hook Form | Override reason text, draft edit textarea |
| Auth state | React Query + httpOnly cookie | Session data fetched from `/api/auth/session` |

### Zustand stores

```ts
// stores/inboxStore.ts
interface InboxStore {
  activeTab: 'urgent' | 'normal' | 'brief' | 'archive';
  selectedMessageId: string | null;
  feedbackModalMessageId: string | null;
  setActiveTab: (tab: InboxStore['activeTab']) => void;
  setSelectedMessageId: (id: string | null) => void;
  openFeedbackModal: (messageId: string) => void;
  closeFeedbackModal: () => void;
}

// stores/draftsStore.ts
interface DraftsStore {
  activeFilter: 'all' | 'pending' | 'approved' | 'rejected';
  editingDraftId: string | null;
  setActiveFilter: (filter: DraftsStore['activeFilter']) => void;
  setEditingDraftId: (id: string | null) => void;
}
```

Zustand state is never persisted to `localStorage` in Prototype (no rehydration needed; all meaningful state lives server-side).

---

## Shared Types

```ts
// types/api.ts — mirrors backend Pydantic schemas

type Priority = 'urgent' | 'normal' | 'brief' | 'archive';

interface TriagedMessage {
  id: string;
  threadId: string;
  sender: { name: string; address: string };
  subject: string;
  snippet: string;
  bodyHtml: string;
  priority: Priority;
  confidence: number;           // 0–1
  rationale: string;
  approved: boolean;
  labelPreview: string[];       // labels to be applied on approval
  hasDraft: boolean;
  receivedAt: string;           // ISO 8601
}

interface DraftWithContext {
  id: string;
  messageId: string;
  threadSubject: string;
  originalSender: { name: string; address: string };
  originalSnippet: string;
  draftBody: string;
  rationale: string;
  status: 'pending' | 'approved' | 'rejected';
  createdAt: string;
}

interface Brief {
  id: string;
  timeWindow: 'morning' | 'afternoon';
  date: string;
  summary: string;
  actionItems: ActionItem[];
  threads: BriefThread[];
  generatedAt: string;
}
```

---

## Error Handling

- API errors surface as toast notifications (shadcn `<Sonner>`).
- 401 errors: redirect to `/login`.
- 5xx errors: toast with retry button; query does not invalidate cache.
- Network offline: React Query suspends background refetches; banner shown ("Reconnecting…").
- No silent failures — every failed mutation shows user-visible feedback.

---

## Accessibility Baseline

- All interactive elements reachable by keyboard (Tab / Enter / Space / Escape).
- Priority badges use color + text label (not color alone).
- Rationale tooltips are also accessible via `aria-describedby`.
- Focus trapped in modals (FeedbackModal, OverridePanel) via `@radix-ui/react-dialog`.
- Minimum contrast ratio: 4.5:1 (WCAG AA) enforced via Tailwind color choices.
- Lighthouse accessibility score target: ≥ 90 (enforced in CI — see deployment architecture).
