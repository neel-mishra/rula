# Runbook: Gmail Watch / Webhook Failure

**Severity**: SEV-2 (brief/triage pipeline degrades; no data loss)
**RTO target**: 60 minutes

## Symptoms
- Gmail push notifications stop arriving (no new emails processed for > 30 min)
- `inbox.emails.ingested` metric flat for active mailbox
- `gmail_watch_expiration` in DB is in the past

## Diagnosis

```bash
# Check watch expiration for all active mailboxes
SELECT id, gmail_email, gmail_watch_expiration, is_active, is_connected
FROM mailboxes
WHERE is_active = true
ORDER BY gmail_watch_expiration ASC;

# Check recent ingestion events
SELECT created_at, event_type, payload->>'email' AS mailbox
FROM audit_events
WHERE event_type LIKE 'auth.%'
ORDER BY created_at DESC LIMIT 20;
```

## Resolution Steps

### Sandbox Path (docker-compose)

1. **Check API/worker service health and logs**:
   ```bash
   cd /Users/neelmishra/.cursor/Rula/AI\ inbox\ chief\ of\ staff
   docker compose -f docker-compose.dev.yml ps
   docker compose -f docker-compose.dev.yml logs --tail=200 api worker
   ```
   - Confirm API router is up and there are no repeated Gmail auth/watch errors.

2. **Probe local webhook route** (`/webhooks/gmail`):
   ```bash
   curl -i -X POST http://localhost:8000/webhooks/gmail \
     -H "Content-Type: application/json" \
     -d '{"message":{"data":""},"subscription":"sandbox-probe"}'
   # Expect 2xx/4xx from app logic, not 5xx or connection refused
   ```

3. **Re-register Gmail watch** via mailbox-connect route (`/mailbox-connect/gmail/*`):
   ```bash
   # Use the Gmail watch re-registration endpoint exposed by mailbox-connect.
   # Replace <MAILBOX_ID> and include auth headers/cookies as required.
   curl -i -X POST "http://localhost:8000/mailbox-connect/gmail/watch/reregister?mailbox_id=<MAILBOX_ID>"
   ```
   - If your local route shape differs (path param vs query), use the equivalent `/mailbox-connect/gmail/*` re-register endpoint implemented in API.

4. **Backfill safely (idempotent) after watch gap**:
   ```bash
   # Reconcile from last known history checkpoint for this mailbox.
   python -m workers.backfill_worker --mailbox-id <MAILBOX_ID>
   ```
   - Run backfill only after watch re-registration succeeds to avoid duplicate operational noise.

### Cloud Path (retain for prod/staging)

1. **Re-register watch** for affected mailbox via renewal job:
   ```bash
   # Trigger watch renewal Lambda / ECS task
   aws lambda invoke --function-name inbox-watch-renewal \
     --payload '{"mailbox_id": "<uuid>"}' /tmp/renewal_result.json
   ```

2. **Verify webhook endpoint** (`/webhooks/gmail`) is reachable:
   ```bash
   curl -X POST https://api.inbox.internal/webhooks/gmail \
     -H "Content-Type: application/json" \
     -d '{"message": {"data": ""}, "subscription": "test"}'
   # Expect: 200 or 400, not 5xx
   ```

3. **Check Google Cloud Pub/Sub delivery errors** in Google Cloud Console:
   - Navigate to Pub/Sub > Subscriptions > inbox-gmail-push
   - Check "Delivery errors" tab for auth/TLS issues

4. **Backfill missed messages** (idempotent):
   ```bash
   # Run history backfill from last known history_id
   python -m workers.backfill_worker --mailbox-id <uuid>
   ```

5. **Confirm watch expiry renewal cron** is running:
   - EventBridge rule: `inbox-watch-renewal` triggers daily at 02:00 UTC
   - Check CloudWatch Logs for last successful run

## Escalation
- If watch cannot be renewed after 3 attempts: escalate to Google Cloud support
- If Pub/Sub subscription is broken: recreate subscription and re-register webhook

## Prevention
- Watch renewal scheduled 24h before expiry with jitter
- Alert: `gmail_watch_expiration_hours < 48` fires P2 alert
- Polling fallback activates if no push notification received for 60 min

## Quick Verification Checklist
- [ ] `docker compose ... ps` shows `api` and `worker` healthy (sandbox) or cloud renewal worker healthy
- [ ] POST probe to `/webhooks/gmail` returns non-5xx
- [ ] Gmail watch re-registration endpoint under `/mailbox-connect/gmail/*` succeeds
- [ ] New Gmail push event observed (logs/metrics no longer flat)
- [ ] Backfill completed for affected mailbox without duplicate side effects
