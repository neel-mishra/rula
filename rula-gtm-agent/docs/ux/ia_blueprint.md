# Information Architecture Blueprint (v1)

## Design Principle

Replace engineering-first tab layout with AE-first task architecture. Every screen answers: "What should I do next?"

## Navigation Model

```
Sidebar (persistent):
  - App title: "Rula Revenue Intelligence"
  - Role selector (admin / analyst / viewer)
  - Role badge (read-only display of current role)
  - Page navigation (radio buttons):
      1. Prospecting (default landing)
      2. MAP Review
      3. Insights
      4. Admin (visible only to admin role)
  - Version label: "v1"
```

## Page 1: Prospecting Workspace (default)

**Purpose**: AE selects an account and gets a send-ready email in < 60 seconds.

```
[Account selector: company name + industry chip]
    |
[Account details expander (collapsed)]
    |
[Run Prospecting button (full width, primary)]
    |
[Spinner: "Running prospecting pipeline..."]
    |
[Result Card]
  ┌─────────────────────────────────────────┐
  │ Outcome: "Prospecting complete for X"   │
  │                                         │
  │ [Audit PASS/REVIEW pill] [Quality 4.2/5]│
  │ [Corrections: 0]                        │
  │                                         │
  │ Why these value props (expanders)       │
  │   - Total Cost of Care (score 80)       │
  │   - EAP Upgrade (score 65)              │
  │                                         │
  │ Unit economics estimate (expander)      │
  │                                         │
  │ ─── Recommended next action ───         │
  │ [SUCCESS: Ready to send]                │
  │ or [WARNING: Review suggested]          │
  │                                         │
  │ Send-ready email:                       │
  │   Subject: ...                          │
  │   Body: ...                             │
  │   CTA: ...                              │
  │   [Copy to clipboard]                   │
  │                                         │
  │ Discovery questions (expander)          │
  │ Flags (expander)                        │
  │ Technical details (expander, collapsed) │
  └─────────────────────────────────────────┘
```

## Page 2: MAP Review

**Purpose**: AE verifies commitment evidence and gets a confidence assessment.

```
[Input mode toggle: "Select sample" | "Structured capture"]
    |
[Evidence selector OR structured capture form]
    |
[Run MAP Verification button (full width, primary)]
    |
[Spinner: "Running MAP verification..."]
    |
[Result Card]
  ┌─────────────────────────────────────────┐
  │ Evidence X → [HIGH (85) pill]           │
  │                                         │
  │ [Audit PASS/REVIEW pill] [Corrections]  │
  │                                         │
  │ Risk factors: [chip] [chip]             │
  │                                         │
  │ Why this confidence tier? (expander)    │
  │   - Threshold explanation               │
  │   - Score breakdown                     │
  │                                         │
  │ ─── Recommended actions ───             │
  │ 1. ...                                  │
  │ 2. ...                                  │
  │                                         │
  │ Technical details (expander, collapsed) │
  └─────────────────────────────────────────┘
```

## Page 3: Insights

**Purpose**: AE and managers review system performance and recent activity.

```
[Pipeline metrics]
  - Prospecting: total runs, success rate, avg latency
  - MAP Verification: total runs, success rate, avg latency

[Provider usage]
  - Claude: N generations
  - Gemini: M generations
  - Fallback rate: X%

[Evaluation baselines]
  - Golden MAP accuracy
  - Prospecting audit pass rate
  - Shadow structural match
```

## Page 4: Admin Panel (role-gated)

**Purpose**: Admin-only operations. Hidden from analyst and viewer roles.

```
[Gate: "Admin access required" if not admin]

[Retention cleanup]
  - Days input + run button

[Shadow compare]
  - Mode toggle: MAP / Prospecting
  - Evidence/account selector
  - Run button + metrics display

[Configuration viewer]
  - Environment, model routing, key status
  - Startup validation warnings
```

## Component Reuse Matrix

| Component | Prospecting | MAP Review | Insights | Admin |
|-----------|------------|------------|----------|-------|
| Confidence pill | x | x | | |
| Result card | x | x | | |
| Technical expander | x | x | | x |
| Copy button | x | | | |
| Metric card | x | x | x | x |
| Spinner | x | x | | x |
| Error banner | x | x | | x |

## Role Visibility Matrix

| Element | admin | analyst | viewer |
|---------|-------|---------|--------|
| Prospecting page | Run | Run | View only (PermissionError) |
| MAP Review page | Run | Run | View only (PermissionError) |
| Insights page | Full | Full | Full |
| Admin page | Full | Hidden | Hidden |
| Role selector | Visible | Visible | Visible |
