#!/usr/bin/env bash
# Non-destructive compose verification checks for sandbox bring-up.
# Read-only operations only: config, ps, and HTTP endpoint probes.

set -eu

COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
COMPOSE_ENV_FILE="${COMPOSE_ENV_FILE:-.env.prod}"
BASE_URL="${BASE_URL:-http://localhost}"
API_HEALTH_URL="${API_HEALTH_URL:-${BASE_URL%/}/health/}"
FRONTEND_URL="${FRONTEND_URL:-$BASE_URL}"
JAEGER_URL="${JAEGER_URL:-http://localhost:16686}"
TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-5}"

if ! command -v docker >/dev/null 2>&1; then
  echo "FAIL: docker is required but not installed or not in PATH."
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "FAIL: docker compose plugin is required. Install Docker Compose v2 and retry."
  exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "FAIL: compose file not found: $COMPOSE_FILE"
  exit 1
fi

if [ ! -f "$COMPOSE_ENV_FILE" ]; then
  echo "FAIL: env file not found: $COMPOSE_ENV_FILE"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "FAIL: curl is required for endpoint checks."
  exit 1
fi

pass() {
  printf 'PASS: %s\n' "$1"
}

warn() {
  printf 'WARN: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

http_code() {
  url="$1"
  code="$(curl -sS -o /dev/null -m "$TIMEOUT_SECONDS" -w "%{http_code}" "$url" || true)"
  if [ -z "$code" ]; then
    printf '000'
    return
  fi
  printf '%s' "$code"
}
compose() {
  docker compose -f "$COMPOSE_FILE" --env-file "$COMPOSE_ENV_FILE" "$@"
}

service_container_id() {
  service="$1"
  compose ps -q "$service" 2>/dev/null | tr -d '[:space:]'
}

container_state() {
  container_id="$1"
  docker inspect --format '{{.State.Status}}' "$container_id" 2>/dev/null || true
}

container_health() {
  container_id="$1"
  docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$container_id" 2>/dev/null || true
}

echo "Running sandbox compose matrix checks (read-only)."
echo "Compose file: $COMPOSE_FILE"
echo "Env file: $COMPOSE_ENV_FILE"

if compose config >/dev/null; then
  pass "compose config resolves"
else
  fail "compose config validation failed"
fi

if compose ps >/dev/null; then
  pass "compose stack is queryable"
else
  fail "unable to query compose stack; is Docker running and stack created?"
fi

services="migrate postgres redis minio api worker frontend caddy jaeger otel-collector pgbackup"
for service in $services; do
  container_id="$(service_container_id "$service")"
  if [ -z "$container_id" ]; then
    fail "service '$service' is not present in current compose project state"
  fi

  state="$(container_state "$container_id")"
  if [ -z "$state" ]; then
    fail "unable to read state for service '$service' (container: $container_id)"
  fi

  case "$service" in
    migrate)
      if [ "$state" = "exited" ]; then
        pass "migrate state is exited (expected one-shot)"
      else
        warn "migrate state is '$state' (expected: exited after successful run)"
      fi
      ;;
    *)
      if [ "$state" = "running" ]; then
        pass "$service state is running"
      else
        fail "$service state is '$state' (expected: running)"
      fi
      ;;
  esac

  health="$(container_health "$container_id")"

  if [ -n "$health" ]; then
    if [ "$health" = "healthy" ]; then
      pass "$service health is healthy"
    elif [ "$health" = "starting" ]; then
      warn "$service health is starting"
    else
      fail "$service health is '$health' (expected: healthy)"
    fi
  fi
done

api_code="$(http_code "$API_HEALTH_URL")"
case "$api_code" in
  200)
    pass "api health endpoint reachable at $API_HEALTH_URL (200)"
    ;;
  *)
    fail "api health endpoint returned $api_code at $API_HEALTH_URL"
    ;;
esac

frontend_code="$(http_code "$FRONTEND_URL")"
case "$frontend_code" in
  200|301|302)
    pass "frontend endpoint reachable at $FRONTEND_URL ($frontend_code)"
    ;;
  *)
    warn "frontend endpoint returned $frontend_code at $FRONTEND_URL"
    ;;
esac

jaeger_code="$(http_code "$JAEGER_URL")"
case "$jaeger_code" in
  200|301|302)
    pass "jaeger endpoint reachable at $JAEGER_URL ($jaeger_code)"
    ;;
  *)
    warn "jaeger endpoint returned $jaeger_code at $JAEGER_URL"
    ;;
esac

echo "Sandbox compose matrix checks completed."
