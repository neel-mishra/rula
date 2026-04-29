# Quality Gate Checklist

## Universal Gates
- [ ] Scope matches approved plan
- [ ] Tests added/updated and passing
- [ ] Lint/type checks passing
- [ ] No unresolved P1 findings

## High-Risk Gates
- [ ] Risk register updated
- [ ] Rollback plan documented and verified
- [ ] Critical domain maturity thresholds met
- [ ] Hard-blocker classes absent (security, integrity, UX critical breakage, silent behavior changes, missing provenance)

## Release Safety
- [ ] Rollout strategy defined (flag/canary/phased)
- [ ] Observability signals defined and checked
- [ ] Owner and approvals recorded

