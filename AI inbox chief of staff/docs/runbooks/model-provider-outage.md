# Runbook: Model Provider Outage / Rate Limit Exhaustion

**Severity**: SEV-2 (drafts/briefs degraded; triage falls back to deterministic)
**RTO target**: 60 minutes

## Symptoms
- `llm.all_providers_failed` log errors spiking
- Draft generation success rate dropping
- `inbox.stage.errors{stage=draft_agent}` metric above baseline
- Brief completion rate falling below 99.5%

## Automatic Behavior (No Manual Action Required Initially)
The system automatically falls back:
1. `anthropic` primary fails → tries `openai` fallback
2. If both fail → triage runs deterministic-only (conservative inbox-keep)
3. Drafts skipped; briefs composed with raw snippets instead of LLM summaries

## Investigation

```bash
# Check provider error pattern
aws logs filter-log-events \
  --log-group-name /inbox/prod/workers \
  --filter-pattern "llm.primary_failed_fallback" \
  --start-time $(date -d '1 hour ago' +%s000)

# Check Anthropic status
curl https://status.anthropic.com/api/v2/status.json | jq '.status.description'

# Check current LLM costs vs budget
SELECT
  sum(extra->>'input_tokens')::int AS total_input,
  sum(extra->>'output_tokens')::int AS total_output,
  count(*) AS requests
FROM audit_events
WHERE event_type = 'draft.generated'
  AND created_at > now() - interval '24 hours';
```

## Resolution

### Rate limit exhaustion
1. Check daily budget consumption:
   ```bash
   aws cloudwatch get-metric-statistics \
     --metric-name inbox.llm.cost_cents \
     --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%SZ) \
     --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
     --period 3600 --statistics Sum
   ```
2. If over budget: degradation mode is automatic at 80% threshold
3. If exhausted: wait for next UTC day reset or increase monthly budget

### Provider outage
1. Verify fallback is working (OpenAI responding)
2. If both providers down: engage `KILL_SWITCH_LLM=true`
   ```bash
   aws ssm put-parameter --name /inbox/prod/KILL_SWITCH_LLM --value "true" --overwrite
   ```
3. Monitor Anthropic status page; re-enable when resolved

## Post-Outage
- Trigger brief backfill for missed windows
- Check memory extraction queue for unprocessed feedback
- Re-enable LLM once confirmed stable
