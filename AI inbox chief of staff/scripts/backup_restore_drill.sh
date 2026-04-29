#!/usr/bin/env bash
# Sandbox backup/restore drill helper.
# Safe by default: runs in dry-run mode unless RUN=1 is set.
#
# Usage:
#   ./scripts/backup_restore_drill.sh
#   RUN=1 ./scripts/backup_restore_drill.sh
#   RUN=1 RESTORE_DB_NAME=drill_restore_20260429 ./scripts/backup_restore_drill.sh

set -eu

RUN="${RUN:-0}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.prod}"
POSTGRES_SERVICE="${POSTGRES_SERVICE:-postgres}"
POSTGRES_USER="${POSTGRES_USER:-app}"
SOURCE_DB_NAME="${SOURCE_DB_NAME:-app}"
RESTORE_DB_NAME="${RESTORE_DB_NAME:-drill_restore}"
ARTIFACT_DIR="${ARTIFACT_DIR:-/tmp/backup-restore-drill}"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
DUMP_FILE="${ARTIFACT_DIR}/backup-${SOURCE_DB_NAME}-${TIMESTAMP}.dump"
BASELINE_COUNTS_FILE="${ARTIFACT_DIR}/baseline-counts-${TIMESTAMP}.txt"
RESTORE_COUNTS_FILE="${ARTIFACT_DIR}/restore-counts-${TIMESTAMP}.txt"

CORE_TABLES="users mailboxes emails triage_decisions drafts briefs memories mutation_ledger"

pass() {
  printf 'PASS: %s\n' "$1"
}

info() {
  printf 'INFO: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

run_cmd() {
  if [ "$RUN" = "1" ]; then
    info "RUN: $*"
    sh -c "$*"
  else
    info "DRY-RUN: $*"
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "required command not found: $1"
  fi
}

compose_prefix="docker compose -f \"$COMPOSE_FILE\" --env-file \"$ENV_FILE\""

extract_counts_sql() {
  db_name="$1"
  output_file="$2"

  : > "$output_file"
  for table in $CORE_TABLES; do
    if [ "$RUN" = "1" ]; then
      count="$(
        sh -c "$compose_prefix exec -T \"$POSTGRES_SERVICE\" psql -U \"$POSTGRES_USER\" -d \"$db_name\" -tAc \"SELECT COUNT(*) FROM $table;\""
      )" || fail "count query failed for table '$table' in db '$db_name'"
      # trim whitespace/newlines from psql output
      count="$(printf '%s' "$count" | tr -d '[:space:]')"
      if [ -z "$count" ]; then
        fail "empty count returned for table '$table' in db '$db_name'"
      fi
      printf '%s=%s\n' "$table" "$count" >> "$output_file"
    else
      printf '%s=<dry-run>\n' "$table" >> "$output_file"
      info "DRY-RUN: query count for table '$table' in db '$db_name'"
    fi
  done
}

compare_counts() {
  baseline_file="$1"
  restored_file="$2"

  mismatch=0
  for table in $CORE_TABLES; do
    baseline="$(awk -F= -v t="$table" '$1==t {print $2}' "$baseline_file")"
    restored="$(awk -F= -v t="$table" '$1==t {print $2}' "$restored_file")"

    if [ -z "$baseline" ] || [ -z "$restored" ]; then
      printf 'MISMATCH: %s missing baseline/restored count\n' "$table" >&2
      mismatch=1
      continue
    fi

    if [ "$baseline" != "$restored" ]; then
      printf 'MISMATCH: %s baseline=%s restored=%s\n' "$table" "$baseline" "$restored" >&2
      mismatch=1
    else
      printf 'MATCH: %s count=%s\n' "$table" "$baseline"
    fi
  done

  if [ "$mismatch" -ne 0 ]; then
    fail "row-count integrity checks failed"
  fi
}

main() {
  require_cmd docker

  mkdir -p "$ARTIFACT_DIR"

  info "Backup/restore drill helper (sandbox)"
  info "RUN=${RUN} (set RUN=1 to execute)"
  info "Artifacts directory: $ARTIFACT_DIR"
  info "Source DB: $SOURCE_DB_NAME | Restore DB: $RESTORE_DB_NAME"

  run_cmd "$compose_prefix ps >/dev/null"

  info "Step 1: capture baseline row counts"
  extract_counts_sql "$SOURCE_DB_NAME" "$BASELINE_COUNTS_FILE"
  info "Baseline counts file: $BASELINE_COUNTS_FILE"

  info "Step 2: create backup dump"
  run_cmd "$compose_prefix exec -T \"$POSTGRES_SERVICE\" pg_dump -U \"$POSTGRES_USER\" -d \"$SOURCE_DB_NAME\" -Fc > \"$DUMP_FILE\""
  info "Backup dump path: $DUMP_FILE"

  info "Step 3: recreate restore database"
  run_cmd "$compose_prefix exec -T \"$POSTGRES_SERVICE\" psql -U \"$POSTGRES_USER\" -d postgres -c \"DROP DATABASE IF EXISTS \\\"$RESTORE_DB_NAME\\\";\""
  run_cmd "$compose_prefix exec -T \"$POSTGRES_SERVICE\" psql -U \"$POSTGRES_USER\" -d postgres -c \"CREATE DATABASE \\\"$RESTORE_DB_NAME\\\";\""

  info "Step 4: restore backup into restore database"
  run_cmd "$compose_prefix exec -T \"$POSTGRES_SERVICE\" pg_restore -U \"$POSTGRES_USER\" -d \"$RESTORE_DB_NAME\" \"$DUMP_FILE\""

  info "Step 5: capture restored row counts"
  extract_counts_sql "$RESTORE_DB_NAME" "$RESTORE_COUNTS_FILE"
  info "Restore counts file: $RESTORE_COUNTS_FILE"

  if [ "$RUN" = "1" ]; then
    info "Step 6: compare baseline and restored counts"
    compare_counts "$BASELINE_COUNTS_FILE" "$RESTORE_COUNTS_FILE"
    pass "backup/restore drill completed with row-count parity"
  else
    info "Dry-run completed. Re-run with RUN=1 for real execution and integrity validation."
  fi
}

main "$@"
