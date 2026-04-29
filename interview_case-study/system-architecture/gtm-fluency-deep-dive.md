# GTM Fluency Deep Dive

This deep dive explains how the system design reflects employer-sales reality, not just technical preference. It connects major architecture decisions to business outcomes across prospecting, MAP verification, and campaign economics.

---

## 1) GTM context this system is built for

The target workflow is employer-channel behavioral health sales, where success depends on:

- choosing the **right value proposition** for each account context,
- converting early interest into **verifiable commitments** (MAP),
- and ensuring campaign execution drives **utilization and unit economics**, not just meetings booked.

The product implication: a GTM system must do more than generate copy; it must help AEs prioritize, message, verify, and route opportunities with explicit confidence and risk handling.

---

## 2) Why this value prop for this account?

### Design choice

Value prop selection is deterministic and account-specific (`src/agents/prospecting/value_prop_scoring.py`), using weighted signals:

- industry/segment rules,
- employee-size breakpoints,
- carrier/plan patterns,
- context buckets from account notes,
- interaction boosts and penalties.

### GTM logic

Employer buyers care about different outcomes by segment:

- Health systems: cost and care utilization pressure -> stronger `total_cost_of_care` framing.
- Universities: access/adoption across student/staff populations -> stronger `employee_access` framing.
- Other segments: wedge chosen from best deterministic signal fit.

### Business outcome

This prevents “generic personalization theater” and improves:

- relevance of first-touch outreach,
- quality of discovery conversation,
- likelihood that the first meeting lands on budget/operations pain, not feature tour.

In employer sales terms: better problem framing increases conversion from intro to real evaluation motion.

---

## 3) Prospecting design choices that map to sales execution

### System choices

- Segment-aware prompt variables (`segment_logic.py`)
- Structured email/questions generation with policy validators (`generator.py`)
- Banned language and claim controls (`prompts.py`, `response_validator.py`)
- Audit + correction loops (`judge.py`, correction paths)
- Human review routing when confidence is weak

### GTM rationale

Employer sales wins when messaging is:

- relevant to employer operating context,
- specific enough to create urgency,
- compliant/safe for external communication,
- consistent across reps.

### Business outcome

This increases AE throughput without collapsing quality:

- less manual drafting time,
- fewer off-brand or risky claims,
- stronger discovery readiness,
- cleaner downstream handoff payloads.

---

## 4) Why this confidence threshold for MAP verification?

### Design choice

MAP verification uses a scored confidence model with tiering (`HIGH`/`MEDIUM`/`LOW`) and risk factors, then applies judge/correction checks. There is also explicit directness logic:

- secondhand evidence cannot remain `HIGH` (tier cap + risk flag),
- language strength and source directness affect tier assignment,
- low-confidence outputs route to review actions.

### GTM rationale

In employer sales, not all commitment language is equal:

- “We’re exploring” is not a committed launch.
- AE-reported Slack snippets are weaker than first-party commitment.
- Overstating confidence creates false pipeline health and forecast distortion.

### Business outcome

Confidence tiering with risk flags improves forecast hygiene:

- better separation of true progress vs noise,
- cleaner manager review and RevOps intervention,
- reduced premature CRM state advancement.

This is critical for enterprise/employer motions where cycle length and stakeholder complexity are high.

---

## 5) How campaign productivity drives unit economics in this design

### Core idea

The system treats “campaign readiness and follow-through” as part of commercial quality, not just messaging output.

Evidence in architecture:

- MAP recommendations link commitment confidence to next actions,
- handoff orchestrators route pass/review/error paths cleanly,
- exports include caveats/review indicators for RevOps decisioning,
- provenance fields preserve what drove recommendations.

### GTM-economic interpretation

Campaign productivity matters because employer-channel economics depend on:

- activation of eligible population,
- sustained utilization (not one-off outreach),
- lower friction to in-network behavioral care,
- repeatable execution across accounts.

If campaigns don’t execute well, acquisition effort does not translate into realized value (for employer or vendor), and unit economics deteriorate.

### Business outcome

The system is designed to favor opportunities where:

- messaging is aligned to the right wedge,
- commitment quality is verifiable,
- execution steps are explicit and trackable.

That improves conversion efficiency and reduces wasted AE/revops cycles.

---

## 6) Design decisions tied directly to employer-sales outcomes

| Design decision | Employer-sales reality | Business outcome |
|---|---|---|
| Deterministic value-prop scoring before generation | Buyer pain differs by segment/size/plan | Better first-meeting relevance and conversion quality |
| Structured discovery-question generation | Discovery discipline determines deal quality | More actionable qualification data earlier |
| MAP confidence tier + risk factors | Pipeline signal quality varies by evidence directness | Better forecast reliability and manager control |
| Audit/review gates | Not every output should auto-progress | Lower risk of bad outreach or bad CRM state updates |
| Review queue + caveats in exports | RevOps needs operational triage, not raw model text | Faster interventions, safer handoffs |
| Deterministic fallback mode | Sales ops cannot pause when providers fail | Operational continuity and predictable throughput |

---

## 7) “Good GTM design” in this system

A GTM-fluent design here is not judged by “best copy.” It is judged by whether the system:

1. chooses account strategy that matches buyer economics,
2. captures commitment quality with realistic confidence semantics,
3. protects operations from false positives and brittle automation,
4. and improves campaign productivity per AE hour.

That is exactly where this architecture points:

- deterministic strategic core,
- constrained generative surfaces,
- explicit confidence and risk handling,
- operational handoff and governance.

---

## 8) Practical takeaway

For employer sales, the winning pattern is:

**Segment-aware strategy -> disciplined messaging -> evidence-based commitment verification -> governed execution handoff.**

This system encodes that pattern directly in code paths and contracts, which is why its design decisions map to real GTM outcomes rather than isolated AI outputs.

