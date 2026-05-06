# UX Flow Map — Prototype (Phase 1)

**Primary persona:** Manager / Operator  
**Scope:** Prototype only. EA/Chief of Staff and IC flows are deferred to MVP.

---

## Persona Overview

| Archetype | Phase | Optimization target |
|---|---|---|
| Manager / Operator | Prototype (PRIMARY) | Thread-to-task conversion, SLA reminders, fast triage decisions |
| Founder / Executive | Prototype (secondary) | One-screen priority view, fast approval, daily brief |
| EA / Chief of Staff | MVP | Delegation and transparency |
| Individual Contributor | MVP | Lightweight use |

---

## Flow 1: Onboarding

Entry point: unauthenticated user arrives at `/`

```
[Landing page /]
  - Value prop headline
  - "Connect Gmail" CTA button
  - No sign-up form — OAuth only
        |
        v
[Google OAuth consent screen]  (hosted by Google)
  - User reviews requested scopes:
      gmail.readonly, gmail.labels, gmail.modify, gmail.compose
  - User clicks "Allow"
        |
        v
[OAuth callback /auth/callback]
  - Server exchanges code for tokens
  - Tokens stored server-side (not in browser)
  - Session cookie set (httpOnly)
        |
        v
[Initial sync screen /onboarding/sync]
  - Progress indicator: "Scanning last 30 days of email…"
  - Background: AI triage pipeline runs first batch
  - No user action required — passive wait state
  - ETA shown ("This takes about 60 seconds")
        |
        v
[Setup complete screen /onboarding/done]
  - Summary card: "Found 47 threads. 6 marked urgent, 28 normal, 13 brief."
  - Single CTA: "Go to Inbox"
        |
        v
[Inbox /inbox]  →  see Flow 2
```

**UX notes:**
- Onboarding is a one-time path; subsequent logins skip to `/inbox` directly.
- If OAuth fails or scope is denied, user lands on an error screen with a retry CTA and a plain-language explanation of why the scopes are needed.

---

## Flow 2: Daily Triage (Primary Flow)

Entry point: authenticated user opens `/inbox`

```
[Inbox /inbox]
  - Default tab: Urgent
  - Tabs: Urgent | Normal | Brief | Archive
  - Each tab shows count badge (e.g. "Urgent 6")
  - Message list auto-polls every 60 seconds for new items
        |
        v
[Message list — triaged cards]
  Each MessageCard displays:
  - Sender name + address
  - Subject line
  - 1-line snippet
  - AI priority badge (URGENT / NORMAL / BRIEF / ARCHIVE) with color coding
  - Confidence indicator (e.g. "92% confident")
  - Rationale tooltip (hover/tap): "Marked urgent because: deadline keyword detected,
    sender is in VIP list"
  - Two action buttons: [Approve triage] [Override]
        |
        |--- user clicks [Approve triage] ------------------------------>
        |     Optimistic UI: badge turns solid, card fades slightly
        |     PATCH /messages/{id}/triage { approved: true }
        |     Card moves to "Approved" state (greyed label strip)
        |     Toast: "Triage approved"
        |
        |--- user clicks [Override] ------------------------------------>
        |     Opens inline override panel (not a separate page):
        |       - Radio buttons: Urgent / Normal / Brief / Archive
        |       - Optional free-text reason field
        |       - [Save override] button
        |     On save: PATCH /messages/{id}/triage { priority: <new>, reason: <text> }
        |     Feedback event written to eval dataset (see Flow 5)
        |     Toast: "Override saved"
        |
        v
[Click a MessageCard to open detail pane]
  - Right panel (desktop) or full-screen (mobile) slides in
  - Full email body rendered (HTML sanitized)
  - AI rationale block at top (always visible, not collapsed):
      "AI Priority: URGENT
       Reason: Contains deadline keyword 'by EOD Friday', sender tagged VIP"
  - Priority badge with confidence score
  - Action buttons: [Approve triage] [Override] [Open in Gmail ↗]
  - If a draft exists for this thread: "Draft ready — review in Drafts queue"
        |
        v
[After action]
  - Returns to message list
  - Processed items remain visible in their tab with an "Approved" or "Overridden" marker
  - No automatic archiving in Prototype — user controls archiving from Gmail
```

**UX constraints enforced here:**
- No send button appears anywhere.
- AI rationale is always visible — never hidden behind a "show why" toggle.
- Labels are shown as a preview before being applied; user must approve before the label is written to Gmail.

---

## Flow 3: Draft Review

Entry point: notification badge on "Drafts" nav item, or user navigates to `/drafts`

```
[Notification entry point]
  - Browser/PWA notification: "New draft ready for review — Re: Budget approval"
  - Click notification → /drafts
        |
        v
[Draft queue /drafts]
  - List of DraftCards, sorted by thread urgency
  - Each card shows: subject, original sender, "Draft ready" badge, timestamp
  - Filter: All | Pending review | Approved | Rejected
        |
        v
[Click DraftCard → Draft detail pane]
  - Original message context block (collapsed by default, expandable):
      - Original sender, subject, full body
  - AI draft block:
      - Full draft body text
      - Editable textarea (edit-in-place — click to activate)
      - Character / word count
  - AI rationale strip:
      "Draft generated using: polite acknowledgment template + extracted action
       items from thread"
  - Action buttons:
      [Approve → Save to Gmail Drafts]   [Edit then Approve]   [Reject draft]
        |
        |--- [Approve] ------------------------------------------------->
        |     POST /drafts/{id}/approve
        |     Draft saved to Gmail Drafts folder via API (NOT sent)
        |     Toast: "Draft saved to Gmail. Open Gmail to send when ready."
        |     Card moves to "Approved" state in queue
        |
        |--- [Edit then Approve] ---------------------------------------->
        |     Textarea becomes active/editable
        |     User edits inline
        |     [Save & Approve] button appears
        |     On save: PATCH /drafts/{id} { body: <edited>, approved: true }
        |     Draft saved to Gmail Drafts with edited content
        |     Toast: "Edited draft saved to Gmail."
        |
        |--- [Reject draft] --------------------------------------------->
              Optional reason field (free text)
              POST /drafts/{id}/reject { reason: <text> }
              Toast: "Draft rejected."
              Card moves to "Rejected" state
```

**UX constraints enforced here:**
- No send button at any point. Copy in toast explicitly directs user to Gmail to send.
- User must explicitly approve before any content is written to Gmail Drafts — no auto-save.
- Editing is always possible before approval; approval of unedited vs. edited drafts is tracked separately for eval.

---

## Flow 4: Brief Reading

Entry point: notification (morning / afternoon), or user navigates to `/brief`

```
[Notification entry point]
  Morning (8 AM local): "Your morning brief is ready — 13 items"
  Afternoon (1 PM local): "Your afternoon brief is ready — 8 items"
  Click notification → /brief
        |
        v
[Brief reader /brief]
  - Header: "Morning Brief — Wednesday Apr 30" (or "Afternoon Brief")
  - Time window badge: "Covers email received 6 AM – 12 PM"

  Section 1 — Summary
  - 3–5 sentence plain-English summary of email activity
  - AI rationale strip: "Summary generated from 13 non-urgent threads"

  Section 2 — Action Items
  - Bulleted checklist extracted from email content
  - Each item shows: task text, source thread subject, sender
  - Checkbox to mark item done (local state only in Prototype — no write-back)
  - "Open original" link per item → opens Gmail thread in new tab

  Section 3 — Non-Urgent Thread Digest
  - Scrollable list of threads bucketed as "Brief"
  - Each entry: sender, subject, 2-line snippet
  - Per-entry actions:
      [Mark read]       → PATCH /messages/{id}/brief-read { read: true }
      [Open original ↗] → opens Gmail thread in new tab
        |
        v
[Bottom of brief]
  - "Mark entire brief as read" button
      → batch PATCH for all unread brief items
      → Toast: "Brief marked as read"
  - "View in inbox" link → /inbox filtered to Brief tab
```

**UX notes:**
- Brief is read-only except for the "mark read" actions.
- If no brief is available yet for the current time window, show a loading skeleton with estimated ready time.
- Historical briefs are accessible via a date picker ("View past briefs").

---

## Flow 5: Feedback / Triage Correction

Entry point: any triage card in inbox (MessageCard or detail pane)

```
[MessageCard in inbox — "Wrong priority?" link]
  - Small secondary link below priority badge on every card
  - Available even after approval (corrections accepted at any time)
        |
        v
[Correction modal — inline overlay]
  Header: "Correct AI priority for this message"

  Current priority shown: URGENT (with rationale)

  Priority selector:
    ( ) Urgent
    ( ) Normal
    (x) Brief        ← user selects
    ( ) Archive

  Optional reason field:
    Placeholder: "Why is this priority wrong? (optional — helps train the model)"
    Free text, 280 char max

  Buttons: [Save correction]   [Cancel]
        |
        v
[On Save]
  POST /feedback { message_id, original_priority, corrected_priority, reason }
  Feedback event written to eval dataset
  Message priority badge updates in place (optimistic)
  Toast: "Correction saved. Thank you — this improves future suggestions."
  Modal closes
```

**UX notes:**
- Feedback is always optional and low-friction — modal is 3 taps at most.
- Reason field is never required; even priority-only corrections are valuable.
- Users can see their correction history in `/settings` (feedback history tab).
- Corrections feed the eval pipeline directly; no manual review gate in Prototype.

---

## Navigation Structure

```
Top nav (persistent, authenticated):
  [Inbox]  [Drafts]  [Brief]  [Settings]
  
  Right side: user avatar → logout

Mobile: bottom tab bar replaces top nav
```

---

## Error and Edge States

| Situation | UI behavior |
|---|---|
| Gmail sync not yet complete | Inbox shows skeleton loader with "Sync in progress" banner |
| API request fails | Toast error with retry button; no silent failures |
| AI triage unavailable (model error) | Message shown without priority badge; "Triage pending" label |
| Draft generation failed | DraftCard shows "Draft unavailable — AI error" with retry button |
| Brief not yet ready | Brief page shows estimated ready time with countdown |
| OAuth token expired | Silent re-auth attempt; if fails, redirect to `/login` with "Session expired" message |

---

## Prototype Scope Boundaries

The following are explicitly out of scope for Prototype and must not appear in the UI:

- Send button or any direct email-sending action
- Delegation or "assign to" features
- Multi-mailbox switching
- Policy editor or rule builder
- Full conversation threading view (single message pane only)
- Mobile app (web responsive only)
