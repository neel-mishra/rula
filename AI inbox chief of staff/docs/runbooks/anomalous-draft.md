# Runbook: Anomalous Draft Behavior

**Severity**: SEV-1 if draft sent (impossible by design) | SEV-2 if quality issue
**RTO target**: 20 min (SEV-1), 60 min (SEV-2)

## Hard Guardrail Confirmation
> **No auto-send path exists. Gmail `send` scope is never requested.**
> Drafts are written to Gmail Drafts API (compose scope only).
> User must manually send from Gmail.

If you believe a draft was auto-sent: verify Gmail scope in Secrets Manager first.

## SEV-2: Draft Quality Issue (hallucination, wrong tone, bad grounding)

### Symptoms
- `draft.hallucination_flag = true` in drafts table
- `grounding_score < 0.6` on sampled drafts
- User reports draft had incorrect facts

### Investigation
```sql
SELECT id, email_id, grounding_score, hallucination_flag,
       style_conformance_score, prompt_version, model_id, created_at
FROM drafts
WHERE mailbox_id = '<mailbox_id>'
  AND (hallucination_flag = true OR grounding_score < 0.6)
  AND created_at > now() - interval '24 hours'
ORDER BY created_at DESC;
```

### Common Causes
| Cause | Fix |
|-------|-----|
| Prompt not grounding in thread | Update DraftAgent prompt to reference thread ID |
| Body extraction failure (HTML only) | Fix `_extract_plain_body` for this email type |
| Email too long; truncated context | Increase context window or chunking |
| Model changed behavior | Pin model version explicitly |

### Immediate Actions
1. Delete affected Gmail drafts from user's account (user to do manually)
2. Disable DraftAgent for this mailbox temporarily:
   ```sql
   UPDATE mailboxes SET draft_enabled = false WHERE id = '<mailbox_id>';
   ```
3. Fix root cause in prompt/extraction logic
4. Run eval suite on fixed version before re-enabling

## After Resolution
- Add problematic email type to EvalAgent gold set
- Update grounding_score threshold if needed
- Record in risk register
