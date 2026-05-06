# Orchestrator Contracts — Inbox Chief of Staff

## Purpose

This document is the single source of truth for:

1. The workflow state machine and valid transitions
2. Typed input/output contracts for every agent
3. The policy enforcement layer (allowed vs. blocked actions)
4. The handoff envelope that wraps every inter-agent message

All agent implementations, orchestrator code, and API response shapes must conform to these contracts. Breaking changes require a version bump and a migration plan.

---

## 1. Workflow State Machine

### States

| State | Description |
|---|---|
| `INGESTED` | Raw Gmail payload fetched and written to GCS |
| `NORMALIZED` | Message fields extracted; `messages` row populated |
| `TRIAGED` | Triage agent has run; `triage_results` row written |
| `DRAFT_QUEUED` | Message classified urgent/normal; draft generation enqueued |
| `BRIEF_QUEUED` | Message classified brief; accumulated for next digest window |
| `FOLLOW_UP_FLAGGED` | Thread identified as requiring follow-up tracking |
| `PENDING_REVIEW` | Draft or brief written; awaiting user accept/reject |
| `COMPLETED` | User accepted action, or message archived with no action required |
| `REJECTED` | User rejected draft, or policy violation halted workflow |

### Valid Transitions

```
INGESTED
  └─► NORMALIZED

NORMALIZED
  └─► TRIAGED

TRIAGED
  ├─► DRAFT_QUEUED          (priority = urgent | normal)
  ├─► BRIEF_QUEUED          (priority = brief)
  ├─► FOLLOW_UP_FLAGGED     (co-occurs with DRAFT_QUEUED or BRIEF_QUEUED)
  └─► COMPLETED             (priority = archive)

DRAFT_QUEUED
  └─► PENDING_REVIEW        (after draft_agent writes draft to Gmail)

BRIEF_QUEUED
  └─► PENDING_REVIEW        (after brief_agent writes digest, triggered by time window)

FOLLOW_UP_FLAGGED
  └─► PENDING_REVIEW        (surfaced in review UI as reminder card)

PENDING_REVIEW
  ├─► COMPLETED             (user accepts)
  └─► REJECTED              (user rejects, or PolicyViolationError raised)
```

### Invariants

- Only `orchestrator/state_machine.py` may call `workflow_repo.update_state()`.
- An invalid transition (e.g. `INGESTED → COMPLETED`) raises `OrchestratorError` and logs an audit event.
- `FOLLOW_UP_FLAGGED` is additive: a workflow run may hold both `DRAFT_QUEUED` and `FOLLOW_UP_FLAGGED` until both resolve.

---

## 2. Agent Input / Output Contracts

All types are defined in `agents/contracts.py`. Pydantic v2 models are used so that validation, serialization, and JSON schema generation are automatic.

### 2.1 Triage Agent

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal

class TriageInput(BaseModel):
    message_id: str                          # internal UUID from messages table
    gmail_message_id: str                    # Gmail API message ID
    subject: str
    sender_email: str
    sender_name: str | None
    body_preview: str = Field(max_length=500)
    thread_id: str
    received_at: datetime

class TriageOutput(BaseModel):
    priority: Literal["urgent", "normal", "brief", "archive"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str                           # one-sentence explanation for audit log
    labels: list[str]                        # Gmail label names to apply
    fallback_used: bool = False              # True if rule engine fired instead of LLM
```

**Confidence fallback rule (implemented in `triage_agent.py`):**

If `confidence < 0.70` after the LLM call, the agent discards the LLM output and runs a deterministic classifier:

1. Sender domain match against `PRIORITY_SENDER_DOMAINS` config list → `urgent`
2. Subject/body keyword scan (`URGENT_KEYWORDS`, `BRIEF_KEYWORDS`) → appropriate priority
3. Default → `normal`

The `fallback_used` flag is set to `True` and the telemetry event records the original LLM confidence alongside the final output.

---

### 2.2 Draft Agent

```python
class DraftInput(BaseModel):
    message_id: str
    gmail_message_id: str
    thread_context: list[dict]               # last 3 turns; each: {role, body, sender}
    user_persona_notes: str | None           # from user profile; injected into system prompt
    tone_guidance: str | None                # e.g. "concise", "formal", "warm"

class DraftOutput(BaseModel):
    draft_body: str
    subject_line: str
    confidence: float = Field(ge=0.0, le=1.0)
    citations: list[str]                     # quoted snippets from thread used as basis
    draft_only: bool = True                  # ALWAYS True in Prototype; enforced by policy
```

**Prototype constraint:** `draft_only` is hardcoded `True` in `draft_agent.py`. Even if a future caller sets it to `False`, `action_policy.py` will block `SEND_EMAIL` at the action layer. Defence-in-depth.

The agent writes the draft to Gmail using `WRITE_DRAFT` (allowed action) by calling `gmail_client.drafts.create()`. The returned `gmail_draft_id` is stored in the `drafts` table.

---

### 2.3 Brief Agent

```python
from typing import Literal

class BriefInput(BaseModel):
    message_ids: list[str]                   # internal UUIDs; 5–50 messages
    time_window: Literal["morning", "afternoon"]
    user_timezone: str                       # IANA tz string, e.g. "America/Los_Angeles"
    user_id: str

class BriefOutput(BaseModel):
    summary_markdown: str                    # rendered in review UI
    action_items: list[str]                  # extracted from urgent/normal messages
    skipped_count: int                       # messages classified archive; not surfaced
    confidence: float = Field(ge=0.0, le=1.0)
```

Brief generation is triggered by a scheduled Cloud Tasks task at 07:00 and 13:00 user-local time. The orchestrator collects all `BRIEF_QUEUED` workflow runs for the user since the last brief, passes their `message_id` list to `brief_agent`, and transitions each constituent workflow run to `PENDING_REVIEW` atomically after the brief is saved.

---

## 3. Policy Enforcement Layer

Defined in `policy/action_policy.py`.

### Allowed Actions

| Action Enum | Description |
|---|---|
| `READ_MESSAGE` | Call `messages.get` or `threads.get` |
| `WRITE_DRAFT` | Create or update a Gmail draft |
| `ADD_LABEL` | Apply a label to a message (informational, not destructive) |

### Blocked Actions

| Action Enum | Reason |
|---|---|
| `SEND_EMAIL` | No autonomous sends in Prototype; human must trigger send from Gmail |
| `DELETE_MESSAGE` | Irreversible; not permitted at any confidence level |
| `ARCHIVE_MESSAGE` | Archive is destructive to user inbox state; reserved for explicit user action |
| `MODIFY_CONTACTS` | Out of scope; prevents accidental CRM pollution |

### Enforcement Behaviour

```python
def check(action: ActionEnum, workflow_run_id: str, agent_name: str) -> None:
    """
    Raises PolicyViolationError if action is blocked.
    Always writes an audit_events row regardless of outcome.
    """
    ...
```

- Called **before** every Gmail API write, without exception.
- On a blocked action:
  1. Raises `PolicyViolationError(action=action, agent=agent_name)`
  2. Writes `audit_events` row: `event_type=POLICY_VIOLATION`, `outcome=BLOCKED`
  3. Caller (orchestrator) catches the error, transitions workflow to `REJECTED`, and returns an error envelope to the review UI.
- On an allowed action:
  1. Writes `audit_events` row: `event_type=ACTION_EXECUTED`, `outcome=ALLOWED`
  2. Returns normally; caller proceeds with the Gmail API call.

---

## 4. Handoff Envelope

Every message passed between the orchestrator and an agent (in both directions) is wrapped in a `HandoffEnvelope`. This enables uniform logging, tracing, and error surfacing.

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

class HandoffEnvelope(BaseModel):
    workflow_id: str                         # workflow_runs.id
    step_id: str                             # UUID generated per agent invocation
    agent_name: str                          # "triage_agent" | "draft_agent" | "brief_agent"
    timestamp: datetime                      # UTC; set by orchestrator at dispatch time
    payload: dict[str, Any]                  # serialized agent input or output
    confidence: float | None = None          # populated on outbound (agent → orchestrator)
    policy_tags: list[str] = Field(          # actions this step is permitted to take
        default_factory=list
    )
    error: str | None = None                 # set if agent raised an exception
```

### Usage pattern

**Orchestrator → Agent (inbound envelope):**

```python
envelope = HandoffEnvelope(
    workflow_id=run.id,
    step_id=str(uuid4()),
    agent_name="triage_agent",
    timestamp=datetime.utcnow(),
    payload=TriageInput(...).model_dump(),
    policy_tags=["READ_MESSAGE", "ADD_LABEL"],
)
result_envelope = triage_agent.run(envelope)
```

**Agent → Orchestrator (outbound envelope):**

The agent receives the inbound envelope, validates `policy_tags` against the actions it needs, calls the LLM, and returns a new envelope with `payload` set to the serialized output and `confidence` populated. On error it returns an envelope with `error` set and `payload={}`.

### Telemetry emitted per envelope

`base_agent.py` emits the following structured log immediately after every LLM call:

```json
{
  "event": "agent_call",
  "workflow_id": "...",
  "step_id": "...",
  "agent_name": "triage_agent",
  "input_hash": "sha256:<hex>",
  "output_hash": "sha256:<hex>",
  "confidence": 0.87,
  "model_version": "claude-sonnet-4-6",
  "latency_ms": 1240,
  "fallback_used": false,
  "timestamp": "2026-04-30T07:14:22Z"
}
```

This event is also persisted to `eval_samples` by `telemetry/eval_harness.py` for offline scoring.

---

## 5. Error Handling Summary

| Error Class | Raised By | Effect |
|---|---|---|
| `PolicyViolationError` | `action_policy.py` | Workflow → REJECTED; audit event written |
| `OrchestratorError` | `state_machine.py` | Invalid transition logged; workflow unchanged |
| `AgentTimeoutError` | `base_agent.py` | Envelope returned with `error` set; orchestrator retries up to 2x then → REJECTED |
| `NormalizationError` | `normalizer.py` | Workflow stays in INGESTED; dead-letter queue alert |
| `ConfidenceFallback` | `triage_agent.py` | Not an error; rule engine fires, `fallback_used=True` |
