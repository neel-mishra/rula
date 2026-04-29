.PHONY: sandbox-smoke sandbox-matrix-check observability-sanity verify-migration-gate

# Day-0 sandbox smoke validation for MVP QA.
# Example:
#   make sandbox-smoke BASE_URL=http://localhost:8000
#   make sandbox-smoke BASE_URL=https://sandbox.example.com SMOKE_EMAIL=qa+smoke@example.com SMOKE_PASSWORD='VeryStrongPass123!'
sandbox-smoke:
	./scripts/sandbox_smoke.sh

# Repeatable read-only compose verification matrix checks.
# Example:
#   make sandbox-matrix-check
#   make sandbox-matrix-check COMPOSE_FILE=docker-compose.prod.yml COMPOSE_ENV_FILE=.env.prod BASE_URL=http://localhost
sandbox-matrix-check:
	./scripts/compose_matrix_check.sh

# Practical API + worker trace sanity validation.
# Example:
#   make observability-sanity BASE_URL=http://localhost:8000
#   make observability-sanity BASE_URL=https://sandbox.example.com JAEGER_URL=http://<vm-ip>:16686
observability-sanity:
	./scripts/observability_sanity.sh

# Static migration gate verification against production compose wiring.
# Example:
#   make verify-migration-gate
#   make verify-migration-gate COMPOSE_FILE=docker-compose.prod.yml
verify-migration-gate:
	./scripts/verify_migration_gate.sh "$${COMPOSE_FILE:-docker-compose.prod.yml}"
