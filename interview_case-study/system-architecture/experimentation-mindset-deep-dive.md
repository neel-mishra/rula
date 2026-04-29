# Experimentation Mindset Deep Dive

This deep dive outlines how to run this system as an experimentable product, not a static workflow. It focuses on measurement, iteration cadence, and concrete response plans when outputs underperform.

---

## 1) What does “working” mean in this system?

A useful experimentation mindset starts with layered success criteria:

1. **System reliability**: pipelines complete, failures are contained, and fallback behavior preserves throughput.
2. **Output quality**: generated/verified outputs pass validation and audit checks.
3. **Operator adoption**: AEs and RevOps actually use outputs in live workflow.
4. **Business impact**: improved conversion quality, cleaner forecast signal, higher campaign productivity.

If you only track one layer (for example, model quality), you can miss the actual business outcome.

---

## 2) Measurement framework (north-star + diagnostics)

### A) Prospecting: primary outcome metrics

- **AE adoption rate**: % of generated emails used with no or minimal edits.
- **Edit distance / override rate**: how often AEs rewrite subject/body/CTA.
- **Review burden**: % routed to review and time-to-approve.
- **Early funnel lift**: response/reply/meeting-booked rates vs baseline.

### B) MAP verification: primary outcome metrics

- **False-positive rate (FPR)**: % high/medium tiers later judged incorrect by human review.
- **Precision at tier**: how often `HIGH` truly reflects commitment-level evidence.
- **Escalation quality**: % low-confidence correctly routed to review.
- **Decision latency**: time from evidence ingestion to usable recommendation.

### C) Platform/ops metrics

- Pipeline success/failure rate (`pipeline_complete` telemetry).
- Fallback activation rates (provider failover + deterministic fallback).
- DLQ/incident volume trends.
- Contract mismatch events and schema drift.

---

## 3) Instrumentation already in this codebase (and how to use it)

Existing hooks you can operationalize:

- `telemetry_events.jsonl` via `src/telemetry/events.py`
- generation-level telemetry (`emit_generation` in `src/telemetry/ux_events.py`)
- bulk run summaries (pass/review/error distributions)
- audit fields (`judge_pass`, `judge_audit_score`, correction attempts)
- correction artifacts (`src/agents/prospecting/corrections.py`)
- review queue artifacts (`handoff.py`, `map_handoff.py`)
- lineage (`lineage.jsonl`) for traceability of decision paths

Best practice: create a weekly experiment dashboard that joins these into:

- adoption funnel,
- quality funnel,
- reliability funnel.

---

## 4) Iteration loop: how to run experiments

Use a short, repeated loop (weekly or biweekly):

1. **Diagnose**  
   Identify top failure mode from data (low AE adoption, high false positives, etc.).

2. **Hypothesize**  
   Example: “Low adoption is caused by overly generic Pattern Interrupt paragraphs.”

3. **Intervene with one controlled change**  
   Change one layer at a time:
   - scoring logic,
   - prompt constraints,
   - validation thresholds,
   - routing/review policy.

4. **Shadow or staged rollout**  
   Use existing shadow comparison and review gating before broad rollout.

5. **Evaluate against pre-registered metrics**  
   Compare to control/baseline; promote only if improvement is durable.

6. **Codify or rollback**  
   Keep winners; revert losers quickly.

---

## 5) If AEs do not use prospecting emails, what to change?

Treat this as a funnel diagnosis, not a single prompt tweak.

### Step 1: Segment the failure

Break non-adoption by:

- segment (health system, university, etc.),
- provider/fallback path,
- review-flag state,
- account data completeness,
- specific edited fields (subject/body/CTA).

### Step 2: Rank likely causes

Common patterns:

- wrong value prop selection,
- generic first paragraph context,
- CTA mismatch to account maturity,
- tone/claim policy over-constraining usefulness.

### Step 3: Intervention menu

1. **Improve deterministic strategy layer first**  
   Adjust scoring weights/rules before touching prompts if relevance is off.

2. **Tighten context injection quality**  
   Improve context-fetching fallback hierarchy to reduce generic language.

3. **Refine prompt contract for sales utility**  
   Keep structure, but tune constraints to increase practical usability.

4. **Use correction memory as supervised signal**  
   Promote frequent AE edits into deterministic rules or policy checks.

5. **Differentiate by segment template**  
   If one segment underperforms, apply segment-specific generation constraints.

### Step 4: Success criteria for promotion

- adoption rate up,
- manual edit depth down,
- no increase in safety/audit failures,
- stable or improved early funnel conversion.

---

## 6) If MAP verifier has too many false positives, how to recalibrate?

False positives here mean overly optimistic confidence tiering for weak evidence.

### Step 1: Build error taxonomy

Label false positives by cause:

- secondhand source misclassified,
- weak commitment language interpreted as firm,
- channel/source reliability overestimated,
- correction loop insufficiently strict.

### Step 2: Recalibration levers

1. **Score threshold tuning**  
   Raise `HIGH` threshold or narrow boundary bands.

2. **Source directness penalties**  
   Increase penalty/cap behavior for secondhand evidence.

3. **Risk-factor gating**  
   Require additional corroboration for high-stakes tiers.

4. **Post-score guardrails**  
   Add explicit downgrade rules when high-risk patterns are present.

5. **Audit gate strictness**  
   Increase correction aggressiveness or reduce max confidence when judge confidence is low.

### Step 3: Validate with precision-focused metrics

- improve precision of `HIGH` tier first,
- monitor recall impact (avoid over-downgrading everything),
- ensure review queue load remains operationally manageable.

Goal: better forecast integrity, not merely lower confidence across all records.

---

## 7) Experiment design patterns to use in this system

### Pattern A: Shadow mode first

- Run new logic in parallel with current logic.
- Compare structural + directional match and downstream review outcomes.
- Promote only after stability window.

### Pattern B: Segment-scoped canary

- Roll out by segment (e.g., health systems first).
- Reduces blast radius and reveals segment-specific effects.

### Pattern C: Human-in-the-loop learning

- Mine AE edits and reviewer outcomes as structured feedback.
- Convert repeated edits into deterministic policy or scoring changes.

### Pattern D: Contract-safe evolution

- Keep schema versions explicit.
- Add fields additively; avoid breaking downstream consumers.

---

## 8) “Good enough” for experimental promotion

A change is “good enough” to ship when:

1. **Reliability** does not regress (error/fallback incidents stable or improved).
2. **Quality** improves on targeted metric (adoption or precision, depending on experiment).
3. **Safety/governance** remains intact (no spike in incidents, policy violations, or review failures).
4. **Operational cost** is acceptable (review queue and correction burden manageable).

Anything else remains an experiment, not a production decision.

---

## 9) Practical operating cadence

Recommended cadence for this system:

- **Daily**: monitor failures, DLQ/incidents, severe regressions.
- **Weekly**: adoption/precision dashboard review + one prioritized experiment.
- **Biweekly**: threshold/rule recalibration review with AE + RevOps input.
- **Monthly**: contract/governance and retention hygiene audit.

This keeps iteration fast while preserving production discipline.

---

## 10) Mindset summary

Experimentation mindset in this context means:

> Treat every pipeline decision (scoring, prompting, thresholds, routing) as a measurable product hypothesis, and iterate with controlled changes tied to AE adoption, MAP precision, and operational safety—not just model output aesthetics.

That is how this system evolves from “working demo” to durable GTM infrastructure.

