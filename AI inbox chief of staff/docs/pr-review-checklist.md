# PR Review Checklist

**Status**: v1
**Applies to**: every PR merged to `main`.
**Shortcut**: paste the skeleton below into the PR description; reviewer
ticks the boxes that apply.

This checklist is a speed bump, not a gate. If an item obviously doesn't
apply (e.g., "no new migrations" on a docs-only PR), write "n/a" rather
than leaving blank.

---

## Paste Skeleton

```markdown
### PR Review Checklist

**Scope**: <one sentence>
**Risk**: low | medium | high

- [ ] Tests added or extended where logic changed
- [ ] Migrations forward + downgrade tested locally
- [ ] No `gmail.send` scope expansion
- [ ] No user-specific data in new log statements, traces, or alert `details`
- [ ] No cross-tenant leakage — every new query filters by `user_id` or `mailbox_id`
- [ ] Mutations go through `MutationLedger` with an undo token
- [ ] LLM calls honor kill switches + per-mailbox budget
- [ ] New env vars added to `.env.example` and `core/config.py`
- [ ] Frontend: `tsc --noEmit` clean and `next build` green
- [ ] Backend: `pytest tests/unit tests/integration` green
- [ ] Docs updated (roadmap, runbooks, threat model) if behavior changed
- [ ] Risk-register row updated if the change closes or adds a risk
```

---

## Categories

### Correctness
1. **Is there a test that would have caught the bug/regression this PR targets?**
2. **Does the test assert on the observable behavior, not the implementation?** A test that passes only because of a specific internal arrangement is fragile.
3. **Does the migration have a real `downgrade()`?** A migration that silently `pass`es on downgrade hides reversibility risk.

### Security + Safety
4. **New attack surface?** OAuth scopes, webhook endpoints, new public routes, new third-party service calls — all require explicit justification in the PR description.
5. **No `gmail.send` scope, ever.** Verified by `tests/unit/test_security.py::test_no_send_scope`.
6. **Prompt templates changed?** If yes, re-run the adversarial suite (`tests/safety/`) and confirm 100% pass before merging.
7. **User content in new logs/traces/alerts?** Reject unless the content is known Class C (metadata) per `data-classification.md` §4.
8. **Kill switches honored?** Every new LLM call path checks `settings.kill_switch_llm`. Every new mutation path checks `settings.shadow_mode`.

### Multi-tenant isolation
9. **Every new query scopes by `user_id` or `mailbox_id`.** Grep the diff: any `select(...).where(...)` that doesn't should have a comment explaining why (e.g., admin endpoint, system-level job).
10. **Ownership validation before acting on another user's row.** The orchestrator pattern is `mailbox.user_id == task.user_id` before any mutation.

### Reliability
11. **New worker path is idempotent.** Replaying the same message twice must produce the same end state. Use existing dedup keys (`gmail_message_id`, mutation correlation IDs) where possible.
12. **External call has a circuit-breaker or retry with backoff.** Tenacity or the in-code circuit breaker are the two supported patterns.
13. **DLQ wiring exists for any new queue.** No new SQS queue without an accompanying dead-letter queue.

### Observability
14. **New log lines use structured logging** (structlog, with `correlation_id` threaded from the task context).
15. **Metrics / SLO impact considered.** If the change affects a numeric launch target, the SLO registry (`core/slo/targets.py`) should reflect it — or there should be a TODO in the PR linking to a follow-up.
16. **Audit events** fire for any mutation, admin action, or policy change.

### Frontend
17. **`tsc --noEmit` + `next build` both green locally.**
18. **New page respects the role-aware sidebar** — admin-only routes gate on `currentUser.role` both in the sidebar and in the page body.
19. **Errors surface via `toast.error`**, not silent catch-and-pass.

### Docs
20. **Roadmap updated** for any feature status change.
21. **Runbook added or amended** for any new incident class this change introduces.
22. **Threat model / data-classification entries** amended if new data types, new sinks, or new external calls are introduced.

---

## Review Tiers

Not every PR gets every question. Tier the review to the risk level:

| Tier | Risk level | Review depth |
|------|-----------|--------------|
| **Light** | Docs, comment/formatting, isolated UI copy | Items 17–19, 20 if applicable |
| **Standard** | Normal feature or bugfix | Items 1–3, 5, 7–12, 14, 17–20 |
| **Deep** | Security-adjacent, migration, new external call, mutation path | All items |

A PR that touches `core/security/`, `core/llm/`, `core/gmail/`, or any
migration file is automatically Deep tier regardless of size.

---

## Self-Review First

Before requesting review, author reads their own diff top-to-bottom and
answers: "If I were reviewing this, what would I push back on?" The most
common findings at this step:

- Unused imports / dead code
- Debug `print()` or `log.info("HERE")` left in
- Comments that describe *what* instead of *why*
- Test names that restate the code instead of the behavior
- `TODO:` with no owner or ticket link

Fix those before opening the PR. Reviewer time is the expensive resource.
