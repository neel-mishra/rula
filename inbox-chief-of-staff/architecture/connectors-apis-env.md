# Connectors, APIs, and Environment Variables

## Phase 1: Prototype

### Connectors/APIs
- Google OAuth + Gmail API
- Primary LLM provider API
- Optional fallback LLM API
- Postgres (with pgvector)
- Queue service
- Object storage
- Basic observability/error tracking

### Environment variables
- `NODE_ENV`
- `APP_BASE_URL`
- `API_BASE_URL`
- `WEBHOOK_BASE_URL`
- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_URI`
- `GMAIL_SCOPES`
- `GMAIL_WATCH_LABELS`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_MODEL_TRIAGE`
- `LLM_MODEL_DRAFT`
- `LLM_MODEL_BRIEF`
- `DATABASE_URL`
- `VECTOR_STORE_MODE`
- `QUEUE_PROVIDER`
- `QUEUE_URL`
- `OBJECT_STORAGE_BUCKET`
- `ERROR_TRACKING_DSN`

## Phase 2: MVP

### Additional connectors/APIs
- Identity/session provider
- Optional external vector store
- Billing provider
- Notifications provider
- Feature flag provider

### Additional environment variables
- `AUTH_PROVIDER`
- `AUTH_ISSUER_URL`
- `AUTH_AUDIENCE`
- `JWT_SIGNING_KEY`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_API_KEY`
- `EMBEDDING_MODEL`
- `RAG_TOP_K`
- `RAG_SCORE_THRESHOLD`
- `PII_REDACTION_ENABLED`
- `POLICY_ENGINE_MODE`
- `BILLING_PROVIDER`
- `BILLING_API_KEY`
- `BILLING_WEBHOOK_SECRET`
- `FEATURE_FLAG_SDK_KEY`

## Phase 3: Production

### Additional connectors/APIs
- SIEM/log archive
- On-call incident alerting
- Backup/DR orchestration
- Optional DLP scanner
- Optional Microsoft Graph (Outlook)

### Additional environment variables
- `CIRCUIT_BREAKER_ENABLED`
- `CIRCUIT_BREAKER_ERROR_RATE_THRESHOLD`
- `KILL_SWITCH_GLOBAL`
- `KILL_SWITCH_TENANT_LIST`
- `SAFE_MODE_DEFAULT`
- `SLO_P95_LATENCY_MS`
- `SLO_ERROR_BUDGET_PERCENT`
- `SECRETS_ROTATION_DAYS`
- `AUDIT_EXPORT_BUCKET`
- `BACKUP_SCHEDULE_CRON`
- `BACKUP_RETENTION_DAYS`
- `RPO_TARGET_MINUTES`
- `RTO_TARGET_MINUTES`

## Connector governance rule
- New connectors require value justification, cost estimate, owner, and rollback plan.
