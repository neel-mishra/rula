# AE Usability Baseline Report

## Method

Lean usability evaluation of the v0 `app.py` interface against 5 simulated AE task scenarios, using the composite persona (Jordan, AE) and the v0 codebase as baseline.

## Task Scenarios Evaluated

| # | Task | v0 Time-to-Complete | Friction Score (1-5) |
|---|------|---------------------|----------------------|
| 1 | Select an account and generate a prospecting email | ~45s | 4 (high) |
| 2 | Understand why a specific value prop was recommended | Not achievable | 5 (critical) |
| 3 | Copy a send-ready email to clipboard | ~30s (manual select-all) | 3 (moderate) |
| 4 | Verify MAP evidence and explain tier to manager | ~60s | 4 (high) |
| 5 | Check recent run history and performance metrics | Not available | 5 (critical) |

## Key Findings

### F1: Navigation is engineering-first, not task-first
- v0 presented 4 tabs: Prospecting, MAP Verification, Shadow compare, MAP capture redesign.
- AEs only need 2 primary workflows. Shadow compare and MAP capture are admin/ops tasks.
- **Impact**: Cognitive overload on first visit; AEs unsure where to start.

### F2: Output is JSON-first, not action-first
- v0 rendered pipeline results as raw JSON blobs with an audit expander.
- AEs must mentally parse JSON to find the email, score, and next step.
- **Impact**: Time-to-value exceeds 60s; most AEs would abandon.

### F3: No explainability in AE language
- v0 showed `judge_pass`, `judge_audit_score` fields without context.
- No rationale for why a value prop was selected or why a confidence tier was assigned.
- **Impact**: AEs cannot explain recommendations to managers; trust deficit.

### F4: No copy/export actions
- v0 had no clipboard copy, no download, no CRM-ready format.
- **Impact**: AEs must manually select and copy text, breaking workflow momentum.

### F5: Admin controls mixed with AE workspace
- v0 sidebar showed role selector and retention cleanup to all users.
- **Impact**: Visual clutter and confusion about what's relevant.

## v1 Usability Hypotheses (Measurable)

| ID | Hypothesis | Metric | Target |
|----|-----------|--------|--------|
| H1 | Page-based nav reduces first-visit confusion | Task 1 completion time | <= 30s |
| H2 | Result cards replace JSON; AE finds email in < 5s | Time to locate email | <= 5s |
| H3 | Value-prop rationale enables AE to explain "why" | Task 2 achievable (yes/no) | Yes |
| H4 | Copy-to-clipboard reduces export friction | Task 3 completion time | <= 5s |
| H5 | Threshold explanation enables AE to brief manager | Task 4 clarity rating | >= 4/5 |
| H6 | Insights page provides run history | Task 5 achievable (yes/no) | Yes |
| H7 | Admin panel hidden from non-admin roles | AE reports no confusion | 0 complaints |

## Prioritized Friction List (Carried Forward)

1. **P0**: Raw JSON output -> human-readable result cards
2. **P0**: No next-step CTA -> explicit recommended action
3. **P0**: Tab overload -> page-based sidebar navigation
4. **P1**: No copy/export -> clipboard copy buttons
5. **P1**: Admin visible to all -> role-gated admin panel
6. **P1**: No loading states -> spinner + progress feedback
7. **P2**: No confidence visualization -> colored tier pills
8. **P2**: No rationale -> explainability panels

## Journey Map Summary

See `docs/ux/journey_map.md` for full stage-by-stage analysis. Key opportunity stages:
- **Stage 4 (Review Output)**: Highest friction. Replace JSON with structured result card.
- **Stage 5 (Act on Output)**: Second highest. Add copy/export actions.
- **Stage 6 (MAP Review)**: Third. Add confidence visualization and threshold rationale.
