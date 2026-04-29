# Compound Engineering Framework

This folder codifies a reusable Compound Engineering operating system for future projects.

It is grounded in:
- The current repository architecture and delivery workflow
- External engineering standards (OWASP ASVS, Google SRE, progressive delivery)
- A strict compounding loop: Plan -> Work -> Review -> Compound

## Navigation

- `00-repo-system-audit.md`: Component-level architecture audit of this repo
- `01-development-process-audit.md`: Delivery process and quality-system audit
- `02-compound-engineering-framework.md`: Core principles, loop contract, and governance model
- `03-operating-model.md`: Day-to-day execution model for features and systems
- `04-templates/`: Reusable templates for planning, review, risk, release, compounding
- `05-checklists/`: Repeatable checklists for environment, quality, review, and handoffs
- `06-project-bootstrap/`: Starter scaffolding and initialization sequence for new projects
- `07-metrics-and-compounding.md`: KPIs and weekly compounding ritual
- `08-roadmap.md`: 30/60/90-day adoption roadmap
- `09-governance-and-triage.md`: P1/P2/P3 model, SLAs, escalation, and ownership rules
- `10-compound-memory-spec.md`: Required metadata and structure for reusable learning artifacts
- `11-system-component-breakout.md`: End-to-end component inventory with maturity scoring rubric
- `12-external-best-practices.md`: External standards and practical adaptation guidance
- `13-example-feature-packet/`: Pre-filled example plan/review/compound artifact set
- `13-example-feature-packet-security/`: Pre-filled security-critical plan/review/compound set
- `14-weekly-rollout-checklist.md`: One-page team rollout checklist for first operational week
- `15-artifact-routing-map.md`: Domain and keyword map used by Cursor enforcement hook/rule
- `15-end-to-end-compound-engineering-sop.md`: End-to-end procedural SOP for Plan → Work → Review → Compound (tool-agnostic)
- `16-enforcement-triage-log.md`: Auto-generated triage log for bypasses and enforcement warnings

## Cursor automation

- `preToolUse` injects a `## Compound Engineering` section into `CreatePlan` and into `Write` calls targeting plan paths (see [`.cursor/hooks.json`](../../.cursor/hooks.json) and [`.cursor/hooks/inject-compound-engineering-pretool.py`](../../.cursor/hooks/inject-compound-engineering-pretool.py)).

## Working Rules

- Each feature/system effort should produce:
  1. A plan artifact
  2. Evidence-backed implementation
  3. Prioritized review findings and resolutions
  4. A compound artifact that teaches the system
- High-risk changes must satisfy domain maturity thresholds before merge.
- Weekly compounding is mandatory: update templates, rules, and memory assets.

## Default Folder Contract for Future Projects

Use this folder as a reference baseline when creating new project-level structures:
- `docs/plans/`
- `docs/reviews/`
- `docs/solutions/`
- `docs/architecture/`
- `docs/runbooks/`
- `todos/`

