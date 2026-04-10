# Meeting Summarizer & Action Protocol

## 1. Metadata Capture
- **Meeting name:** {{MEETING_TITLE}}
- **Participants:** {{ATTENDEES}}
- **Date and context:** {{DATE_AND_CONTEXT}} (Discovery, MAP planning, weekly GTM review, etc.)

## 2. Executive Summary (Bottom line)
- **One-sentence goal:** {{WHY_WE_MET}}
- **Key outcome:** {{BIGGEST_TAKEAWAY}}
- **Sentiment check:** {{TEAM_STATE}} (Aligned, uncertain, blocked, etc.)

## 3. Decision Log
- **[Decision 1]:** {{DECISION}} | **Rationale:** {{RATIONALE}}
- **[Decision 2]:** {{DECISION}} | **Rationale:** {{RATIONALE}}

## 4. The Action Matrix
| Action Item | Owner | Priority | Deadline | Linked File |
| :--- | :--- | :--- | :--- | :--- |
| {{TASK_1}} | {{OWNER}} | {{P1/P2/P3}} | {{DATE}} | {{@ops/prd.md or related}} |

## 5. Strategic Implications
- **Impact on roadmap:** {{ROADMAP_IMPACT}}
- **Messaging shift needed?:** {{IMPACT_TO_MESSAGING_PILLARS}}
- **MAP/forecast implication:** {{COMMITMENT_CONFIDENCE_IMPACT}}

---
### AI Agent Context Rule
When summarizing transcripts:
1. Ignore small talk.
2. Prioritize statements beginning with "we decided," "we will," "we need," or explicit commitment language.
3. If commitment evidence is ambiguous, mark as follow-up required.
4. Cross-reference priorities with `@core/business_context.md` and `@core/ideal_customer_profile.md`.
