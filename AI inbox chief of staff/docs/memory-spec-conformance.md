# Memory-Spec Conformance Audit

**Status**: v1
**Owner**: `<owner>`
**Date**: 2026-04-25
**Spec under audit**: `/Users/neelmishra/.cursor/Rula/skills/compound-engineering/10-compound-memory-spec.md`
**Roadmap item**: G.9 (Phase 3–5 governance gate)
**Companions**: `quality-gates.md`, `risk-register.md`, `pr-review-checklist.md`

---

## 1. Scope

The Compound Memory Spec defines how solved problems become reusable
system memory — what metadata they carry, what content sections they
contain, and the quality bar (findable / reusable / verifiable /
system-updating). It is a doc-artifact spec, not an ORM spec.

This project has two kinds of "memory":

1. **Compound artifacts** — durable docs in `docs/` (threat model, data
   classification, runbooks, risk register, PIR notes, this review
   packet). The spec applies directly here.
2. **Runtime user-preference memory** — the `Memory` ORM table populated
   by `MemoryAgent` from feedback / instruction / behavioral signals,
   read by `TriageAgent`, `DraftAgent`, `PolicyAgent`. The spec applies
   *in spirit* (findability, reusability, verifiability) but the ORM
   schema is not bound to the spec's metadata fields.

This audit covers both.

---

## 2. Spec Requirements Summary

**Required YAML metadata** (compound artifacts):
`title`, `owner`, `date`, `tags`, `component_domains`, `risk_tier`,
`related_files`, `related_prs`.

**Required content sections** (compound artifacts):
1. Problem pattern + trigger conditions
2. Solution pattern + rationale
3. Prevention rules + guardrails
4. Validation evidence
5. System updates (templates / checklists / rules changed)

**Quality bar**: findable, reusable, verifiable, system-updating.

---

## 3. Conformance Matrix — Compound Artifacts (`docs/`)

| # | Artifact | Frontmatter | Sections 1–5 | Quality bar | Status |
|---|----------|-------------|--------------|-------------|--------|
| 3.1 | `docs/threat-model.md` | Status/Scope/Owner header (no YAML) | Asset/Threat/Mitigation/Gap structure satisfies §1–4; §5 partial (threat model itself updates other docs) | Findable, reusable, verifiable | PARTIAL |
| 3.2 | `docs/data-classification.md` | Status/Scope/Owner header (no YAML) | Per-class Storage/Retention/Redaction/Deletion rows satisfy §1–4 implicitly; §5 covered via deletion-workflow updates | Findable, reusable, verifiable | PARTIAL |
| 3.3 | `docs/risk-register.md` | Status/Cadence/Owner header | Each row = problem (likelihood/impact) + mitigation + residual + owner; aligns with §1–3; §4 is implicit (status as evidence); §5 partial | Findable, reusable | PARTIAL |
| 3.4 | `docs/incident-operations.md` | Status/Scope/Owner header | Severity matrix + PIR template = §1–5 essentially; §5 explicit (PIR drives system updates) | Findable, reusable, verifiable, system-updating | PASS (contentwise) |
| 3.5 | `docs/runbooks/*.md` (4 files) | Title + scope only | §1 trigger conditions present; §2–3 instructions; §4–5 mostly missing | PARTIAL |
| 3.6 | `docs/quality-gates.md` | Status/Scope/Owner header | Gate criteria + waiver template = §3 + §4; §1–2 implicit | Findable, reusable, verifiable | PARTIAL |
| 3.7 | `docs/release-readiness.md` | Status/Scope header | Checklist-as-prevention; §4 evidence built into items; §1 thin | PARTIAL |
| 3.8 | `docs/launch-decision-memo-template.md` | Template instructions | Template — instantiated per-launch; satisfies §1–5 once filled | PASS (as template) |
| 3.9 | `docs/pr-review-checklist.md` | Status/Scope header | Checklist-as-prevention; §1 thin; §2 implicit; §3 strong | PARTIAL |
| 3.10 | `docs/review-template.md` | Status/Scope header | Per-phase review template; satisfies §1–5 by section once instantiated | PASS (as template) |
| 3.11 | `docs/reviews/phase-{0,1,2}-review.md` | Header table | Phase scope (§1) + waivers (§3 prevention) + sign-off (§4) + risk delta (§5) | PASS |
| 3.12 | This document | Header section | Audit follows §1–5 implicitly | PASS |
| 3.13 | `docs/memory-spec-conformance.md` (this file) | Header section | §1 scope, §2 spec, §3 audit, §4 gaps, §5 system updates | PASS |

### Aggregate result for compound artifacts

| Status | Count |
|--------|-------|
| PASS | 5 |
| PARTIAL | 7 |
| GAP | 0 |

The dominant gap is **YAML frontmatter** — none of the existing docs use
the spec's literal frontmatter schema. Content shape mostly satisfies
§1–5 but in operational table form, not the named-section form.

---

## 4. Conformance Matrix — Runtime Memory (`Memory` ORM)

The spec's principles, mapped onto the runtime memory system:

| # | Principle | Implementation site | Status | Notes |
|---|-----------|---------------------|--------|-------|
| 4.1 | **Findable**: memories indexed for retrieval | `core/models/memory.py:39–42` indexes on `(user_id, scope)`, `(mailbox_id, memory_type)`, `(user_id, is_active)`; pgvector `embedding` column with IVFFlat (migration 002) | PASS | |
| 4.2 | **Findable**: scope-aware lookup | `subagents/memory.py:153–159` enforces `mailbox_specific` + `user_global ∧ applies_to_all_mailboxes` only | PASS | |
| 4.3 | **Findable**: semantic + fallback | `MemoryQueryAgent._semantic_search` + `_text_search` (memory.py:146–230) | PASS | Cosine-distance with confidence-ordered fallback |
| 4.4 | **Reusable**: structured payload | `Memory.structured_data` JSONB (memory.py:67) carries `{rule, targets}` for downstream agents | PARTIAL | Free-text `content` still does most of the work; rule extraction quality depends on LLM JSON adherence |
| 4.5 | **Reusable**: scope routing | `MemoryAgent._execute` (memory.py:65–69) gates `user_global` on explicit user phrase ("all mailboxes" / "everywhere") | PASS | |
| 4.6 | **Reusable**: typed taxonomy | `MemoryType` enum (`profile / policy / style / sender`) | PASS | |
| 4.7 | **Verifiable**: provenance trail | `Memory.source` + `source_feedback_id` FK (memory.py:71–78) | PASS | |
| 4.8 | **Verifiable**: evidence preserved | `FeedbackEvent.raw_content` referenced via `source_feedback_id` | PARTIAL | Evidence is *referenced*, not snapshotted. If the linked `FeedbackEvent` row is later purged by retention worker, the memory loses its evidence anchor. |
| 4.9 | **Verifiable**: confidence scoring | `Memory.confidence` (memory.py:81) + decay worker | PASS | |
| 4.10 | **Verifiable**: cross-mailbox safety | `if scope=mailbox_specific then mailbox_id is set` enforced at write (memory.py:69) | PASS | |
| 4.11 | **Verifiable**: write-time audit event | No `AuditEvent` row emitted on Memory create/update/delete | GAP | Memory CRUD bypasses the immutable audit log. Mutations to runtime user state should be auditable. |
| 4.12 | **System-updating**: feedback loop | `api/routers/feedback.py` correction → MemoryAgent → behavior change in next triage | PASS | |
| 4.13 | **System-updating**: behavioral signals | `workers/behavioral_signals.py` undo / correction / edit → MemoryAgent | PASS | |
| 4.14 | **System-updating**: decay + expiry | `workers/memory_decay.py` 5%/week decay, deactivation at 0.3 (memory_decay.py:18–21) | PASS | |
| 4.15 | **System-updating**: protected-sender pathway | `Memory.structured_data` with `rule=always_inbox` consumed by `AlwaysInboxRule` | PASS | |
| 4.16 | **Findable**: tagging / component_domains | No first-class `tags` or `component_domains` columns; tagging is folded into free-text `content` | PARTIAL | |
| 4.17 | **Findable**: title field | No `title` column; `content` doubles as the title | PARTIAL | |
| 4.18 | **Verifiable**: risk_tier | No `risk_tier` field; all memories carry equal weight beyond `confidence` | GAP | Spec calls out `risk_tier`. Runtime memory ignores it — a "always reply within 24h" rule and a "prefer concise emails" rule have no risk distinction. |
| 4.19 | **Reusable**: confidence threshold on read | `TriageAgent` uses memories with `confidence ≥ 0.5`; `DraftAgent` consumes top-k regardless of confidence floor | PARTIAL | Inconsistency between consumers — see Gap §5.3. |
| 4.20 | **System-updating**: prevention-rule path | `PolicyAgent` compiles assistant instructions into rule-shaped memories that downstream rules apply | PASS | |

### Aggregate result for runtime memory

| Status | Count |
|--------|-------|
| PASS | 13 |
| PARTIAL | 5 |
| GAP | 2 |

---

## 5. Gaps + Remediations

### 5.1 (4.11 GAP) — Memory CRUD is not audit-logged

**Gap**: `MemoryAgent._execute` writes a row into `memories` without
emitting an `AuditEvent`. The same applies to manual edit / delete
endpoints in `api/routers/memories.py`.

**Why it matters**: Runtime memory directly steers autonomous mutations
(archive / label). A silent memory mutation that flips a triage outcome
days later is currently traceable only by joining `feedback_events`,
`memories`, and `mutation_ledger` — there is no single source of truth
for "who changed what behavior, when".

**Remediation**: Emit `AuditEvent(actor, target_type=Memory, action,
before_state, after_state)` from MemoryAgent + manual CRUD endpoints.
Add a unit test asserting audit row written on create / update /
deactivate. Sized: ~40 LOC + 1 test.

**Tracked**: open as a Gate 6.a follow-up; not a launch blocker (mutation
ledger captures the *effect* on user mail; this is observability for the
*input* to triage). Add to risk register if not closed by Phase 6 sign-off.

### 5.2 (4.18 GAP) — No `risk_tier` on runtime memory

**Gap**: Spec mandates `risk_tier`. The Memory model has no equivalent.
Memories with high mutation impact ("always archive sender X") and low
impact ("prefer cc rather than bcc") are weighted only by `confidence`,
which decays uniformly.

**Why it matters**: Decay worker treats both equally. Hard rules ("never
auto-reply to legal@…") should not fade with the same 5%/week rate as
soft preferences.

**Remediation**: Add `risk_tier: enum[low, medium, high, hard]` column.
`hard` memories never decay (only deactivate on explicit user delete).
Migration adds the column with default `medium`. `MemoryAgent._execute`
infers tier from `memory_type` (sender = high; profile = low) with LLM
override. `memory_decay.py` skips `hard` and slows `high`. Sized: ~80
LOC + migration + 2 tests.

**Tracked**: open as Phase 5 gate follow-up. Affects roadmap item 5.10
(memory confidence decay).

### 5.3 (4.19 PARTIAL) — Consumer-side confidence threshold inconsistent

**Gap**: `TriageAgent` filters memories by `confidence ≥ 0.5`;
`DraftAgent` and `PolicyAgent` consume top-k without a floor.

**Why it matters**: A barely-active memory (confidence 0.31) can still
influence draft tone or policy compilation, undermining the decay
guarantee.

**Remediation**: Centralize the floor in `core/config.py` as
`memory_min_active_confidence: float = 0.4` and apply in
`MemoryQueryAgent._semantic_search` + `_text_search` so every consumer
inherits it. Sized: ~20 LOC + 1 test.

**Tracked**: open as Phase 5 gate follow-up.

### 5.4 (4.8 PARTIAL) — Evidence not snapshotted

**Gap**: `Memory.source_feedback_id` is a foreign key, not a snapshot.
`workers/data_retention.py` purges old `feedback_events` after 180 days;
the linked memory then loses its anchor.

**Remediation**: At memory write, copy a redacted slice of the feedback
into `Memory.structured_data["evidence_snapshot"]`. Reuse
`core/security/pii.py:scrub_string`. Sized: ~30 LOC + 1 test.

**Tracked**: open as Phase 5 gate follow-up.

### 5.5 (Doc gap) — Compound docs lack YAML frontmatter

**Gap**: None of the existing `docs/*.md` files use the spec's literal
YAML frontmatter (`title / owner / date / tags / component_domains /
risk_tier / related_files / related_prs`). They use a leading
`**Status**` / `**Scope**` / `**Owner**` block instead.

**Why it matters**: Frontmatter unblocks tooling: a future `make
audit-docs` could verify completeness mechanically; it also normalizes
ingestion if/when these get fed into a knowledge base.

**Remediation**: Adopt a transition rule — *new* compound docs use YAML
frontmatter; existing docs can be migrated incrementally on next major
edit. The PR review checklist (`pr-review-checklist.md`) should add a
line for "if creating or substantially editing a compound doc, include
frontmatter."

**Tracked**: open as Phase 7 follow-up. Cosmetic, not blocking.

---

## 6. System Updates Triggered by This Audit

Per spec §5 ("system updates"), this audit changes the system:

- **`docs/pr-review-checklist.md`**: add YAML-frontmatter line for new
  compound docs. *(Pending — flagged in §5.5.)*
- **`risk-register.md`**: open follow-up rows for §5.1, §5.2, §5.3, §5.4
  if not addressed by Phase 5/6 sign-off.
- **`core/config.py`**: introduce `memory_min_active_confidence` setting
  per §5.3.
- **`core/models/memory.py`**: candidate column additions per §5.2 + §5.4.
- **`MemoryAgent` / manual memory CRUD**: emit `AuditEvent` per §5.1.

---

## 7. Re-audit Cadence

This document is re-run on:

- Any migration that touches `memories` or its FKs.
- Any change to `MemoryAgent`, `MemoryQueryAgent`, `memory_decay`, or
  `behavioral_signals`.
- Before each launch (Gate 7) — re-verify all PASS rows still PASS.
- Quarterly post-launch; sooner on any sev1+ incident traced to memory.

---

## 8. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineering | `<owner>` | 2026-04-25 | _______________ |
| Product / Owner | `<owner>` | 2026-04-25 | _______________ |

Audit confirms the runtime memory subsystem conforms to the spec's
spirit (13 PASS, 5 PARTIAL, 2 GAP). Compound-doc frontmatter is the
dominant cosmetic gap. Two GAPs (`risk_tier`, audit logging) are
tracked as Phase 5/6 follow-ups; neither blocks Gate 7 absent
incident-driven escalation.

---

## Change Log

- `2026-04-25 (v1)`: Initial conformance audit covering 13 compound
  artifacts and 20 runtime-memory principles. Five remediations queued
  (§5.1–§5.5).
