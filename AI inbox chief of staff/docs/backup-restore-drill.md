# Backup/Restore Drill (Sandbox)

This runbook defines an executable, deterministic backup/restore drill for the sandbox stack.

Use it to satisfy release-readiness evidence for:

- "Backup/restore drill passed in staging within the last 30 days" (`docs/release-readiness.md`)

## Scope and safety

- Environment: sandbox only (never production from this runbook).
- Backend: Postgres in `docker-compose.prod.yml`.
- Safety default: helper script is **dry-run** unless `RUN=1` is explicitly set.
- Deterministic checks: row counts are captured before backup and compared after restore.

## Prerequisites

- Stack is up from repo root:
  - `docker compose -f docker-compose.prod.yml --env-file .env.prod up -d`
- `docker` and compose plugin installed.
- Operator can run `docker compose ... exec`.
- Choose a restore target database name that does not collide with active app DB (default: `drill_restore`).

## Core integrity tables

The drill checks row counts for these core tables:

- `users`
- `mailboxes`
- `emails`
- `triage_decisions`
- `drafts`
- `briefs`
- `memories`
- `mutation_ledger`

## Run the drill

From repo root:

1. Ensure helper script is executable (one-time per checkout):
   - `chmod +x scripts/backup_restore_drill.sh`
2. Review planned commands (dry-run, default):
   - `./scripts/backup_restore_drill.sh`
3. Execute the drill:
   - `RUN=1 ./scripts/backup_restore_drill.sh`
4. Optional custom restore DB:
   - `RUN=1 RESTORE_DB_NAME=drill_restore_20260429 ./scripts/backup_restore_drill.sh`

## What the helper script does

When `RUN=1`, script performs:

1. Snapshot baseline row counts from core tables in source DB.
2. Create a compressed backup dump from source DB.
3. Drop/recreate restore DB inside Postgres container.
4. Restore dump into restore DB.
5. Snapshot row counts from restore DB.
6. Compare baseline vs restore counts and fail on any mismatch.
7. Print PASS/FAIL guidance and artifact paths.

## Evidence collection

Capture these artifacts in your release evidence:

- Script output log with timestamp.
- Baseline counts file.
- Restored counts file.
- Backup artifact path used for restore.
- Operator name/date and sandbox host.

Suggested command for a durable log:

- `RUN=1 ./scripts/backup_restore_drill.sh | tee /tmp/backup-restore-drill-$(date +%Y%m%d-%H%M%S).log`

## Failure handling

- If any command fails, the script exits non-zero.
- If row counts mismatch, treat as drill failure and block launch until resolved.
- Re-run in dry-run mode to inspect intended command sequence.
- Check Postgres container logs:
  - `docker compose -f docker-compose.prod.yml --env-file .env.prod logs postgres`

## Notes

- Row-count parity is a minimum integrity gate; schema-level and spot-content checks can be added later.
- The script deliberately avoids destructive actions unless `RUN=1` is provided.
