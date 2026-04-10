# Panel Talk Track

## 1) 60-second setup

- Goal: improve Rula GTM execution quality without risking live systems.
- Approach: dual-path architecture (Prospecting + MAP Verification) with audit/safety wrappers.
- Principle: deterministic first, then promote to live only after shadow confidence.

## 2) Demo sequence (8-10 minutes)

1. **Prospecting tab**
   - Run an account with sparse contact data.
   - Show quality score, flags, and judge audit fields.
2. **MAP Verification tab**
   - Run Evidence A/B/C and call out expected tiers.
   - Explain source directness and blocker impact.
3. **Shadow compare tab**
   - Show production vs shadow parity metrics.
   - Tie to promotion criteria thresholds.
4. **MAP capture redesign tab**
   - Enter structured MAP fields.
   - Compile and verify output live.
5. **Sidebar controls**
   - Switch role to `viewer` to show RBAC denial.
   - Trigger retention cleanup as governance operation.

## 3) Quality and risk story

- Audit loop catches weak outputs and retries at most two times.
- Safety controls prevent runaway behavior and preserve traceability.
- Incidents + DLQ provide operational visibility.
- No live writes in prototype mode.

## 4) Scale-up plan

- Replace heuristic judge with provider abstraction + model fallback.
- Add async worker/DLQ replay for high-volume reliability.
- Add policy-as-code for role and retention constraints.
- Introduce experiment registry to track MAP capture redesign outcomes.

## 5) Likely panel Q&A anchors

- **Why agents over monolith?** Better specialization, debuggability, and safer checkpoints.
- **How do you prevent hallucinations?** Bounded deterministic logic + source-aware guardrails.
- **How would you productionize?** Shadow gate, promotion criteria, incident SLOs, retention automation.
