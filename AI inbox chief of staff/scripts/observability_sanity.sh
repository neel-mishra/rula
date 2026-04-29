#!/usr/bin/env bash
# Practical observability sanity checks for API + worker tracing.
# This script is intentionally non-invasive: it only reads env/config and probes
# local endpoints; it does not send data to external SaaS services.
#
# Usage examples:
#   ./scripts/observability_sanity.sh
#   BASE_URL="https://sandbox.example.com" JAEGER_URL="http://127.0.0.1:16686" ./scripts/observability_sanity.sh
#   EXPECT_JAEGER=0 ./scripts/observability_sanity.sh

set -eu

BASE_URL="${BASE_URL:-http://localhost:8000}"
JAEGER_URL="${JAEGER_URL:-http://localhost:16686}"
EXPECT_JAEGER="${EXPECT_JAEGER:-1}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.prod}"

BASE_URL="${BASE_URL%/}"
JAEGER_URL="${JAEGER_URL%/}"

if ! command -v curl >/dev/null 2>&1; then
  echo "FAIL: curl is required but not installed."
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

echo "Running observability sanity checks"
echo "- BASE_URL=$BASE_URL"
echo "- JAEGER_URL=$JAEGER_URL"
echo "- EXPECT_JAEGER=$EXPECT_JAEGER"
echo "- COMPOSE_FILE=$COMPOSE_FILE"
echo "- ENV_FILE=$ENV_FILE"

echo
echo "1) OTEL endpoint environment visibility"

otel_visible=0

if [ -n "${OTEL_EXPORTER_OTLP_ENDPOINT:-}" ]; then
  pass "shell env exposes OTEL_EXPORTER_OTLP_ENDPOINT=${OTEL_EXPORTER_OTLP_ENDPOINT}"
  otel_visible=1
else
  warn "shell env does not set OTEL_EXPORTER_OTLP_ENDPOINT"
fi

if [ -f "$ENV_FILE" ]; then
  env_value="$(awk -F= '/^[[:space:]]*OTEL_EXPORTER_OTLP_ENDPOINT=/{print substr($0, index($0,$2)); exit}' "$ENV_FILE" || true)"
  if [ -n "$env_value" ]; then
    pass "$ENV_FILE contains OTEL_EXPORTER_OTLP_ENDPOINT=$env_value"
    otel_visible=1
  else
    warn "$ENV_FILE does not define OTEL_EXPORTER_OTLP_ENDPOINT"
  fi
else
  warn "$ENV_FILE not found (set ENV_FILE to your env file if needed)"
fi

if command -v docker >/dev/null 2>&1 && [ -f "$COMPOSE_FILE" ]; then
  if docker compose -f "$COMPOSE_FILE" ps >/dev/null 2>&1; then
    for service in api worker; do
      if docker compose -f "$COMPOSE_FILE" ps --status running "$service" >/dev/null 2>&1; then
        service_otel="$(docker compose -f "$COMPOSE_FILE" exec -T "$service" /bin/sh -c 'printf "%s" "${OTEL_EXPORTER_OTLP_ENDPOINT:-}"' 2>/dev/null || true)"
        if [ -n "$service_otel" ]; then
          pass "$service container '$service' sees OTEL_EXPORTER_OTLP_ENDPOINT=$service_otel"
          otel_visible=1
        else
          warn "$service container '$service' is running but OTEL_EXPORTER_OTLP_ENDPOINT is empty"
        fi
      else
        warn "service '$service' not running (skipping container env probe)"
      fi
    done
  else
    warn "docker compose unavailable for $COMPOSE_FILE (skipping container env probe)"
  fi
else
  warn "docker or $COMPOSE_FILE missing (skipping container env probe)"
fi

if [ "$otel_visible" -eq 1 ]; then
  pass "at least one OTEL endpoint source is visible"
else
  fail "OTEL_EXPORTER_OTLP_ENDPOINT not visible in shell/env file/containers"
fi

echo
echo "2) Jaeger UI reachability"

if [ "$EXPECT_JAEGER" = "1" ]; then
  jaeger_code="$(curl -sS -o /dev/null -w "%{http_code}" "$JAEGER_URL" || true)"
  case "$jaeger_code" in
    200|301|302|307|308)
      pass "Jaeger UI reachable at $JAEGER_URL (status: $jaeger_code)"
      ;;
    *)
      fail "Jaeger UI unreachable at $JAEGER_URL (status: $jaeger_code). Check jaeger/otel-collector services."
      ;;
  esac
else
  echo "SKIP: Jaeger reachability check disabled (EXPECT_JAEGER=$EXPECT_JAEGER)"
fi

echo
echo "3) API health + trace inspection guidance"

health_code="$(curl -sS -o /dev/null -w "%{http_code}" "$BASE_URL/health/" || true)"
if [ "$health_code" = "200" ]; then
  pass "API health endpoint reachable at $BASE_URL/health/ (200)"
else
  fail "API health endpoint check failed at $BASE_URL/health/ (status: $health_code)"
fi

cat <<EOF
NEXT:
- Generate trace traffic:
  curl -sS "$BASE_URL/health/" >/dev/null
  curl -sS "$BASE_URL/health/ready" >/dev/null
- Open Jaeger Search:
  $JAEGER_URL/search
- Look for service names:
  inbox-cos-api
  inbox-cos-worker-ingest
  inbox-cos-worker-scheduler
- If traces are missing, inspect logs:
  docker compose -f "$COMPOSE_FILE" logs --tail=100 api worker otel-collector jaeger
EOF

echo
echo "Observability sanity checks completed."
