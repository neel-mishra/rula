# Sandbox Compose Verification Matrix

This checklist is for repeatable, non-destructive validation of a running sandbox stack launched with `docker-compose.prod.yml`.

Run automated checks:

- `make sandbox-matrix-check`
- or `COMPOSE_FILE=docker-compose.prod.yml COMPOSE_ENV_FILE=.env.prod ./scripts/compose_matrix_check.sh`

## Service Verification Matrix

- `migrate`
  - Expected health indicator: one-shot job exits successfully (`docker compose ps --status exited migrate`) with exit code `0`.
  - Remediation:
    - Re-run migration: `docker compose -f docker-compose.prod.yml --env-file .env.prod run --rm migrate`
    - Inspect output: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs migrate`
    - Confirm DB credentials in `.env.prod` (`POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`).

- `postgres`
  - Expected health indicator: container `running` and `healthy` in compose status.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs postgres`
    - Verify volume space/permissions for `postgres_data`.
    - Validate DB settings in `.env.prod`.

- `redis`
  - Expected health indicator: container `running` and `healthy` in compose status.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs redis`
    - Confirm `REDIS_PASSWORD` in `.env.prod` matches expected runtime value.

- `minio`
  - Expected health indicator: container `running` in compose status.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs minio`
    - Confirm `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` values and free disk for `minio_data`.

- `api`
  - Expected health indicator: container `running`; endpoint `GET /health/` returns HTTP `200`.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs api`
    - Validate app secrets/env config (`APP_SECRET_KEY`, DB/Redis URLs, LLM and Gmail keys).
    - Confirm `migrate`, `postgres`, `redis`, and `minio` are healthy first.

- `worker`
  - Expected health indicator: container `running` in compose status.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs worker`
    - Verify queue backend and upstream dependencies (Redis/DB/MinIO/API settings).

- `frontend`
  - Expected health indicator: container `running`; UI endpoint responds with HTTP `200`, `301`, or `302`.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs frontend`
    - Validate `NEXT_PUBLIC_API_URL` and frontend build/runtime env vars.

- `caddy`
  - Expected health indicator: container `running`; base URL responds (often `200`, `301`, or `302`).
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs caddy`
    - Verify `APP_DOMAIN`, DNS A record, and open ports `80/443`.
    - Confirm `Caddyfile` is mounted and valid.

- `jaeger`
  - Expected health indicator: container `running`; UI endpoint on `:16686` returns HTTP `200`.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs jaeger`
    - Confirm host firewall/security group allows `16686` as needed.

- `otel-collector`
  - Expected health indicator: container `running` in compose status.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs otel-collector`
    - Validate mounted config file `infra/otel-collector.yml`.

- `pgbackup`
  - Expected health indicator: container `running` in compose status.
  - Remediation:
    - Review logs: `docker compose -f docker-compose.prod.yml --env-file .env.prod logs pgbackup`
    - Confirm backup env vars and storage space for `pgbackup_data`.

## Notes

- The matrix check script is intentionally read-only: it runs `docker compose config`, `ps`, and HTTP probes only.
- The script does not call `up`, `down`, `start`, `stop`, `restart`, `exec`, or any write operation.
