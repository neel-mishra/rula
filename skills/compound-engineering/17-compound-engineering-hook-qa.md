# Compound Engineering hook QA

Use this pack to confirm **Compound Engineering** shows up as a structural part of plans and plan-like writes—not only as a reminder in chat.

## Automated run (from repo root)

```bash
python3 skills/compound-engineering/qa/test_ce_hook_injection.py
```

Expect: `All N cases passed.` If anything fails, inspect `.cursor/hooks/inject-compound-engineering-pretool.py` and `.cursor/hooks.json` (matcher includes `CreatePlan|Write|ApplyPatch`).

After changing hooks, **reload Cursor hooks** or restart Cursor before manual QA.

---

## What “good” looks like in Cursor

| Surface | Expectation |
|--------|-------------|
| **Plan / CreatePlan** | Body contains `## Compound Engineering` with **Inferred domain** and artifact bullets. |
| **Write** to `*.plan.md`, `.cursor/plans/*.md`, or `**/docs/plans/**/*.md` | Same section appended (after YAML frontmatter if present). |
| **ApplyPatch** targeting those paths | `Add File`: CE woven into `+` lines; `Update File`: extra hunk appended when a context line exists after `@@`. |
| **Explicit override** | Your prompt includes `domain:<name>` (e.g. `domain:security`) → injected block uses that domain even if other keywords appear. |

---

## Manual prompt pack (different architectures)

Paste each block into the agent as a **single user message**. Use **planning mode** or any flow that produces a **CreatePlan** or a **plan markdown file** so `preToolUse` can run.

### 1) Security / zero trust

> You are the tech lead. Design a **zero-trust** internal API: **OAuth2**, **RBAC**, **token** rotation, and **secret** management. Produce a phased implementation plan with components, threat model summary, and test strategy. Save the plan as a markdown plan file if your environment supports it.

**Check:** Inferred domain should lean **security**; CE section lists security-oriented artifacts.

### 2) Data integrity / migrations

> Architect a **schema** evolution for a payments subsystem: backward **compatibility**, **validation** rules, **migration** strategy, and rollback. Output a plan with milestones and risk register.

**Check:** **data-integrity** domain; bullets reference plan / release templates where configured.

### 3) Observability / SRE

> Design **observability** for a new microservice: **metrics**, **logs**, **tracing**, **dashboards**, and **alert** routing. Include on-call runbook outline in the plan. (Avoid putting **SLO** in the plan *title* if you want the hook to infer **observability**—the substring `slo` currently maps to **reliability** first. You can also set `domain:observability` in the prompt.)

**Check:** **observability** domain (or use `domain:observability` for a deterministic check).

### 4) Release management

> Plan a **canary** **rollout** with **feature flags**, **deploy** pipeline gates, and **go-live** checklist. Tie each gate to verification evidence.

**Check:** **release-management** domain.

### 5) Reliability / incidents

> Propose architecture improvements for **reliability**: **error budget**, **incident** playbooks, **rollback**, and **failover** between regions. Plan should include blast-radius analysis.

**Check:** **reliability** domain.

### 6) Ingestion

> Design an **ingestion** pipeline: **import** from partner feeds, **normalize** records, **parse input** errors, and idempotent writes. Include data-quality checks in the plan.

**Check:** **ingestion** domain.

### 7) Output / handoff

> Architect **export** jobs and **downstream** **connector** **payload** **delivery** with retries, signing, and consumer **handoff** documentation.

**Check:** **output-handoff** domain.

### 8) Governance / compliance

> Draft a **compliance**-oriented design: **retention**, **provenance**, **audit trail**, **policy** enforcement, and **triage** for exceptions. No security keywords—should still get a sensible default domain.

**Check:** **governance** (or explicit keywords from corpus).

### 9) Explicit domain override (edge case)

> Plan a small UI tweak. In your first line, write exactly: `domain:security` then describe unrelated work. The Compound Engineering block should honor **security** routing despite unrelated text.

**Check:** `**Inferred domain:** `security``.

### 10) Implementation follow-through (Write / ApplyPatch)

> Take the plan you just produced and implement the first milestone in code. When you edit or create plan markdown under `.cursor/plans/` or `*.plan.md`, confirm the tool payload still gains or preserves the CE section.

**Check:** File on disk after agent writes shows `## Compound Engineering` (hook injects on write/patch if missing).

---

## Known limitations (for fair QA)

- **ApplyPatch `Update File`**: injection appends a hunk only if there is at least one **context line** (diff line starting with a single space) after `@@`. Pure `+`/`-` hunks may not get an append.
- Some Cursor versions may **ignore `updated_input`** for certain tools; if CE never appears, compare with automated script results—if the script passes, the hook is fine and the IDE path may be the gap.

---

## Triage

If enforcement or injection surprises you, append a line to `skills/compound-engineering/16-enforcement-triage-log.md` with date, prompt summary, and observed behavior.
