# Gap implementation runbook (operational)

## Phase 0 — baseline capture

Record one line (ticket / PR / notes):

```text
Original build captured: YYYY-MM-DD | git tag: baseline/original-build @ <SHA> | backup: /path/to/rula-gtm-agent.original-build
```

Use a **git tag** when the repo is under git; otherwise use a **sibling folder** copy per [gap plan § Baseline](../../interview_case-study/rula-gtm-agent_gap-implementation_plan.md).

## Phase gates (1–6)

For each phase after code is green (`pytest -q`), complete **UAT** in Streamlit and explicit **APPROVED** before treating the phase as closed. See the gap plan **§ Phase gates** for the sign-off block and per-phase checklists.

## Revert

To restore the pre-plan tree, follow **§ Baseline: “original build” and revert** in the same gap plan document.
