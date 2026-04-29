# Runbook: False-Archive Spike

**Severity**: SEV-1 (user trust impacted; potentially missing important emails)
**RTO target**: 20 minutes from detection

## Definition
False-archive rate > 0.5% of auto-archived emails in a rolling 7-day window,
OR multiple user-reported "should stay in inbox" corrections in < 1 hour.

## Immediate Response (< 5 min)

1. **Engage kill switch — halt all autonomous mutations immediately**:
   ```bash
   # Set environment variable (triggers restart via ECS rolling deploy)
   aws ssm put-parameter \
     --name /inbox/prod/KILL_SWITCH_MUTATIONS \
     --value "true" \
     --overwrite
   ```

2. **Notify user** if reachable:
   > "We've detected an issue with automatic email routing and have paused all
   > automatic label/archive actions. Your inbox is now in read-only mode for
   > automated actions. No further emails will be moved without your approval."

## Investigation (< 20 min)

```sql
-- Find recent false archives: user manually moved back to inbox
SELECT ml.id, ml.email_id, ml.created_at, ml.reason_trace,
       ml.policy_version, ml.model_version, td.confidence
FROM mutation_ledger ml
JOIN triage_decisions td ON td.email_id = ml.email_id
WHERE ml.mailbox_id = '<mailbox_id>'
  AND ml.status = 'applied'
  AND ml.created_at > now() - interval '24 hours'
ORDER BY ml.created_at DESC;

-- Count false-archive rate
SELECT
  count(*) FILTER (WHERE fe.feedback_type = 'triage_correction') AS corrections,
  count(*) AS total_triage,
  round(count(*) FILTER (WHERE fe.feedback_type = 'triage_correction')::numeric
    / nullif(count(*), 0) * 100, 2) AS false_rate_pct
FROM triage_decisions td
LEFT JOIN feedback_events fe ON fe.email_id = td.email_id
WHERE td.mailbox_id = '<mailbox_id>'
  AND td.created_at > now() - interval '7 days';
```

## Triage: Common Root Causes

| Cause | Signal | Fix |
|-------|--------|-----|
| Model drift / new prompt | Spike after deploy | Roll back prompt version |
| Newsletter rule over-matching | High confidence, rule_matched='newsletter_brief' | Tighten newsletter detection features |
| VIP sender not in memory | Corrections from specific sender | Add to always_inbox memory |
| Confidence threshold too low | confidence=0.70-0.75 batch | Raise TRIAGE_MEDIUM_CONFIDENCE_THRESHOLD |

## Remediation

1. Undo all affected mutations within the blast window:
   ```bash
   python -m scripts.bulk_undo --mailbox-id <uuid> --since "2h ago" --dry-run
   # Confirm, then:
   python -m scripts.bulk_undo --mailbox-id <uuid> --since "2h ago" --execute
   ```

2. Add affected senders to always_inbox memory if warranted

3. Adjust confidence threshold if systematic:
   ```bash
   aws ssm put-parameter \
     --name /inbox/prod/TRIAGE_MEDIUM_CONFIDENCE_THRESHOLD \
     --value "0.85" --overwrite
   ```

4. Re-enable mutations after confirming root cause fixed

## Post-Incident
- Write PIR within 24 hours
- Update risk register
- Add to EvalAgent adversarial sample set
