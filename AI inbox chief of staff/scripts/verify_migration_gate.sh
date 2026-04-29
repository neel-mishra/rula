#!/usr/bin/env bash
# Validate migration gate wiring in docker-compose.prod.yml.
# This check is static (non-docker) and safe to run in CI/local.

set -eu

COMPOSE_FILE="${1:-docker-compose.prod.yml}"

pass() {
  printf 'PASS: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

if [ ! -f "$COMPOSE_FILE" ]; then
  fail "compose file not found: $COMPOSE_FILE"
fi

if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 is required for YAML parsing"
fi

python3 - "$COMPOSE_FILE" <<'PY'
import re
import sys
from pathlib import Path

compose_path = Path(sys.argv[1])
content = compose_path.read_text(encoding="utf-8")


def fail(msg: str) -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    raise SystemExit(1)


def service_block(name: str) -> str:
    pattern = rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [a-zA-Z0-9_-]+:\n|^volumes:|\Z)"
    match = re.search(pattern, content)
    if not match:
        fail(f"service '{name}' is missing")
    return match.group(1)


def assert_in_block(block: str, needle: str, reason: str) -> None:
    if needle not in block:
        fail(reason)


migrate = service_block("migrate")
assert_in_block(migrate, 'command: ["alembic", "upgrade", "head"]', "migrate must run alembic upgrade head")
assert_in_block(migrate, 'restart: "no"', "migrate must be one-shot with restart: \"no\"")
assert_in_block(
    migrate,
    "depends_on:\n      postgres:\n        condition: service_healthy",
    "migrate must depend on healthy postgres",
)

for service_name in ("api", "worker"):
    block = service_block(service_name)
    assert_in_block(
        block,
        "depends_on:\n      migrate:\n        condition: service_completed_successfully",
        f"{service_name} must wait for migrate completion (service_completed_successfully)",
    )

print("PASS: migration gate wiring is present and deterministic in docker-compose.prod.yml")
PY

pass "verified migration gate compose wiring in $COMPOSE_FILE"
