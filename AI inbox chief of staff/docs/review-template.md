# Per-Phase Review Packet (Template)

**Status**: v1
**Scope**: Per-phase gate review. Instantiate one packet per phase (0–7)
under `docs/reviews/phase-N-review.md`. A phase is **closed** only when
this packet is filled out, signed off, and any waivers carry a
compensating control per `quality-gates.md`.
**Consumed by**: `release-readiness.md` (rolls up phase sign-offs into
launch decision).
**Owner**: `<owner>`

---

## Header

| Field | Value |
|-------|-------|
| Phase | `<N — name>` |
| Packet date | `YYYY-MM-DD` |
| Author | `<owner>` |
| Reviewers | `<names>` |
| Roadmap snapshot SHA | `<git sha>` |
| Related risks | `<R# from risk-register.md>` |

---

## 1. Phase Scope

Pull the phase's feature table from `docs/PRODUCT_ROADMAP.md`. List each
roadmap ID with its current status and a one-line evidence pointer (file,
PR, dashboard).

| Roadmap ID | Feature | Status | Evidence |
|------------|---------|--------|----------|
| `<X.Y>` | `<name>` | PASS / PARTIAL / TODO | `<file:line / PR# / link>` |

---

## 2. Gate Criteria

Mirror the gate's row table from `docs/quality-gates.md`. Each row is
either `PASS`, `PARTIAL`, `BLOCKED`, or `WAIVED`. `PARTIAL` and `BLOCKED`
must be addressed in §5.

| # | Criterion | Verification | Status |
|---|-----------|--------------|--------|
| `N.a` | `<criterion>` | `<test / file / dashboard>` | PASS / PARTIAL / BLOCKED / WAIVED |

---

## 3. Acceptance Evidence

Concrete artifacts that prove the phase shipped:

- **Tests**: `pytest <selector>` — `<N passed>` on commit `<sha>`
- **Migrations**: `<migration N>` applied cleanly to dev + integration DB
- **Integrations**: `<service>` smoke run — `<result>`
- **Dashboards**: `<link to /slo/status or CloudWatch dashboard>`
- **PRs merged into main during this phase**: `<PR# list>`

---

## 4. Risk Delta

| Risk ID | Title | Pre-phase status | Post-phase status | Notes |
|---------|-------|------------------|-------------------|-------|
| `R#` | `<title>` | OPEN/CLOSED/MITIGATED | OPEN/CLOSED/MITIGATED | `<change driver>` |

New risks introduced this phase (added to `risk-register.md`):

| Risk ID | Title | Score | Owner |
|---------|-------|-------|-------|
| `R#` | `<title>` | `<L×I>` | `<name>` |

---

## 5. Outstanding Items / Waivers

Anything not PASS in §2 lands here.

### Waiver: `<criterion id>`
- **Reason**: `<why this is acceptable to defer>`
- **Compensating control**: `<what reduces residual risk>`
- **Revisit date**: `YYYY-MM-DD`
- **Owner**: `<name>`
- **Tracked in**: `risk-register.md::R#` or `<follow-up PR/issue>`

---

## 6. Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Engineering | `<name>` | `YYYY-MM-DD` | _______________ |
| Product / Owner | `<name>` | `YYYY-MM-DD` | _______________ |

I confirm every PASS row in §2 has verifiable evidence in §3 and every
non-PASS row has a waiver in §5 with a compensating control. Phase is
closed for the purposes of advancing to the next phase gate.

---

## Change Log

- `YYYY-MM-DD (v1)`: Phase closed at commit `<sha>`. `<one-line summary>`.
