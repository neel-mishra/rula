# Load Tests (k6, local)

Closes roadmap item **X.6**. Validates launch-target SLO latencies +
Gate 6 resilience without cloud credentials.

All scenarios run against `docker-compose.dev.yml` (postgres + redis +
localstack SQS/S3 + api + worker). Thresholds are sourced from
`core/slo/targets.py`.

---

## Prerequisites

```bash
brew install k6
docker compose -f docker-compose.dev.yml up -d
```

Wait for `curl -fsS http://localhost:8000/health` to return 200.

## Mint a load-test JWT (one-time per shell)

The `/slo/status`, `/assistant/instruction`, and admin endpoints require
a Bearer JWT. Mint one for an existing dev user:

```bash
poetry run python -c "
from core.security.auth import create_session_token
from core.models.user import UserRole
import uuid
print(create_session_token(uuid.UUID('00000000-0000-0000-0000-000000000001'), 'load@example.com', UserRole.ADMIN))
" > /tmp/load_jwt
export LOAD_TEST_JWT=$(cat /tmp/load_jwt)
```

The webhook scenario reuses `GMAIL_WEBHOOK_SECRET` directly:
```bash
export GMAIL_WEBHOOK_SECRET=dev-secret
export LOAD_API_BASE=http://localhost:8000
```

## Seed test mailboxes (manual, one-time)

The test runner assumes at least 5 connected mailboxes for the user
identified by `LOAD_TEST_JWT`. Use the dashboard or hit
`POST /mailboxes` with payload `{"email": "...", "label": "loadtest-N"}`
five times.

## Run

```bash
# Smoke (~1 minute total)
k6 run tests/load/scenarios/webhook-spike.js
k6 run tests/load/scenarios/slo-endpoint-load.js

# Full sweep (~10 minutes; uses LLM credits — staging only)
k6 run tests/load/scenarios/orchestrator-throughput.js
k6 run tests/load/scenarios/assistant-throughput.js
```

Or all in one shot:

```bash
make load-test    # alias documented in pyproject.toml comment / project Makefile
```

## What we're validating

| Scenario | SLO target source | Threshold |
|----------|-------------------|-----------|
| `webhook-spike` | webhook intake | p95 < 2s, p99 < 5s, error rate < 1% |
| `orchestrator-throughput` | `core/slo/targets.py` ingest_to_triage_p95=60s, p99=180s | indirect via SLO endpoint after sustained 50 RPS |
| `slo-endpoint-load` | aggregation read path | p95 < 1.5s, error rate < 1% |
| `assistant-throughput` | `core/slo/targets.py` (LLM-bound) | p95 < 8s — manual / staging only |

## Open TODOs

- **JWT minting from k6**: today the operator shells out to poetry to
  mint a token. A native k6 HS256 helper (jslib.k6.io/jwt) would let us
  drop the manual step.
- **Live LLM**: `assistant-throughput.js` hits real Anthropic by
  default. Run only against staging or with `KILL_SWITCH_LLM=true` in
  the API process to exercise the deterministic fallback path.
- **Worker observability**: the orchestrator-throughput scenario reads
  ingest-to-triage latency through `/slo/status`, which is a 5-min
  rolling window. Tighten by tailing `worker` container logs (out of
  scope for k6; use a separate `make tail-load`).
