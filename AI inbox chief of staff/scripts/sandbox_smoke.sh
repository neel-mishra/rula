#!/usr/bin/env bash
# Day-0 sandbox smoke checks for MVP QA.
# Ensure executable bit is set once after checkout: chmod +x scripts/sandbox_smoke.sh
#
# Usage examples:
#   BASE_URL="http://localhost:8000" ./scripts/sandbox_smoke.sh
#   BASE_URL="https://sandbox.example.com" ./scripts/sandbox_smoke.sh
#   BASE_URL="https://sandbox.example.com" SMOKE_EMAIL="qa+smoke@example.com" SMOKE_PASSWORD="VeryStrongPass123!" ./scripts/sandbox_smoke.sh

set -eu

BASE_URL="${BASE_URL:-http://localhost:8000}"
SMOKE_EMAIL="${SMOKE_EMAIL:-}"
SMOKE_PASSWORD="${SMOKE_PASSWORD:-}"
CHECK_WEBHOOKS="${CHECK_WEBHOOKS:-1}"
SAVE_EVIDENCE="${SAVE_EVIDENCE:-0}"
EVIDENCE_DIR="${EVIDENCE_DIR:-}"

if ! command -v curl >/dev/null 2>&1; then
  echo "FAIL: curl is required but not installed."
  exit 1
fi

HAS_JQ=0
if command -v jq >/dev/null 2>&1; then
  HAS_JQ=1
fi

BASE_URL="${BASE_URL%/}"

tmp_body="$(mktemp)"
cleanup() {
  rm -f "$tmp_body"
}
trap cleanup EXIT INT TERM

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
EVIDENCE_ENABLED=0
EVIDENCE_PATH=""
SUMMARY_FILE=""
RESPONSES_DIR=""

if [ "$SAVE_EVIDENCE" = "1" ]; then
  EVIDENCE_ENABLED=1
  if [ -n "$EVIDENCE_DIR" ]; then
    EVIDENCE_PATH="$EVIDENCE_DIR"
  else
    EVIDENCE_PATH="$REPO_ROOT/artifacts/smoke-evidence-$(date -u +%Y%m%dT%H%M%SZ)"
  fi
  mkdir -p "$EVIDENCE_PATH"
  RESPONSES_DIR="$EVIDENCE_PATH/responses"
  mkdir -p "$RESPONSES_DIR"
  SUMMARY_FILE="$EVIDENCE_PATH/endpoint-status-summary.tsv"
  printf 'check\tmethod\turl\tstatus\tresult\n' > "$SUMMARY_FILE"
fi

pass() {
  printf 'PASS: %s\n' "$1"
}

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

redacted_value() {
  key="$1"
  value="$2"
  case "$key" in
    *PASSWORD*|*SECRET*|*TOKEN*|*KEY*)
      if [ -n "$value" ]; then
        printf '%s' '<redacted>'
      else
        printf '%s' '<empty>'
      fi
      ;;
    *)
      if [ -n "$value" ]; then
        printf '%s' "$value"
      else
        printf '%s' '<empty>'
      fi
      ;;
  esac
}

write_env_metadata() {
  if [ "$EVIDENCE_ENABLED" != "1" ]; then
    return
  fi
  metadata_file="$EVIDENCE_PATH/command-env-metadata.txt"
  {
    echo "timestamp_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "script=$0"
    echo "pwd=$(pwd)"
    echo "uname=$(uname -a)"
    echo "has_jq=$HAS_JQ"
    echo "check_webhooks=$(redacted_value CHECK_WEBHOOKS "$CHECK_WEBHOOKS")"
    echo "save_evidence=$(redacted_value SAVE_EVIDENCE "$SAVE_EVIDENCE")"
    echo "evidence_dir=$(redacted_value EVIDENCE_DIR "$EVIDENCE_PATH")"
    echo "base_url=$(redacted_value BASE_URL "$BASE_URL")"
    echo "smoke_email=$(redacted_value SMOKE_EMAIL "$SMOKE_EMAIL")"
    echo "smoke_password=$(redacted_value SMOKE_PASSWORD "$SMOKE_PASSWORD")"
    echo "curl_version=$(curl --version 2>/dev/null | awk 'NR==1{print $0}')"
  } > "$metadata_file"
}

save_response_snippet() {
  check_name="$1"
  method="$2"
  url="$3"
  status="$4"
  result="$5"
  if [ "$EVIDENCE_ENABLED" != "1" ]; then
    return
  fi

  snippet_file="$RESPONSES_DIR/${check_name}.txt"
  {
    echo "check=$check_name"
    echo "method=$method"
    echo "url=$url"
    echo "status=$status"
    echo "result=$result"
    echo "body_snippet=$(body_preview)"
  } > "$snippet_file"
  printf '%s\t%s\t%s\t%s\t%s\n' "$check_name" "$method" "$url" "$status" "$result" >> "$SUMMARY_FILE"
}

write_evidence_manifest() {
  if [ "$EVIDENCE_ENABLED" != "1" ]; then
    return
  fi
  {
    echo "evidence_dir=$EVIDENCE_PATH"
    echo "files:"
    echo "- endpoint-status-summary.tsv"
    echo "- command-env-metadata.txt"
    echo "- responses/*.txt"
  } > "$EVIDENCE_PATH/README.txt"
}

request_code() {
  method="$1"
  url="$2"
  data="${3:-}"
  auth="${4:-}"

  if [ -n "$data" ] && [ -n "$auth" ]; then
    code="$(curl -sS -o "$tmp_body" -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $auth" \
      --data "$data" \
      "$url")" || return 1
  elif [ -n "$data" ]; then
    code="$(curl -sS -o "$tmp_body" -w "%{http_code}" -X "$method" \
      -H "Content-Type: application/json" \
      --data "$data" \
      "$url")" || return 1
  elif [ -n "$auth" ]; then
    code="$(curl -sS -o "$tmp_body" -w "%{http_code}" -X "$method" \
      -H "Authorization: Bearer $auth" \
      "$url")" || return 1
  else
    code="$(curl -sS -o "$tmp_body" -w "%{http_code}" -X "$method" "$url")" || return 1
  fi

  printf '%s' "$code"
}

body_preview() {
  if [ ! -s "$tmp_body" ]; then
    printf '<empty body>'
    return
  fi

  if [ "$HAS_JQ" -eq 1 ]; then
    jq -c . "$tmp_body" 2>/dev/null || tr '\n' ' ' < "$tmp_body"
  else
    tr '\n' ' ' < "$tmp_body"
  fi
}

echo "Running sandbox smoke checks against: $BASE_URL"
write_env_metadata
write_evidence_manifest
if [ "$EVIDENCE_ENABLED" = "1" ]; then
  echo "Evidence capture enabled: $EVIDENCE_PATH"
fi

# 1) Health endpoint reachable
health_code="$(request_code GET "$BASE_URL/health/")" || fail "health endpoint request failed at $BASE_URL/health/"
if [ "$health_code" = "200" ]; then
  save_response_snippet "health" "GET" "$BASE_URL/health/" "$health_code" "PASS"
  pass "health endpoint reachable (200)"
else
  save_response_snippet "health" "GET" "$BASE_URL/health/" "$health_code" "FAIL"
  fail "health endpoint unexpected status: $health_code, body: $(body_preview)"
fi

# 2) Auth register/login endpoint reachable
auth_token=""
if [ -n "$SMOKE_EMAIL" ] && [ -n "$SMOKE_PASSWORD" ]; then
  register_payload=$(printf '{"email":"%s","password":"%s","display_name":"smoke-user"}' "$SMOKE_EMAIL" "$SMOKE_PASSWORD")
  register_code="$(request_code POST "$BASE_URL/auth/register" "$register_payload")" || fail "register request failed"
  case "$register_code" in
    201|409)
      save_response_snippet "auth-register" "POST" "$BASE_URL/auth/register" "$register_code" "PASS"
      pass "register endpoint reachable ($register_code)"
      ;;
    *)
      save_response_snippet "auth-register" "POST" "$BASE_URL/auth/register" "$register_code" "FAIL"
      fail "register endpoint unexpected status: $register_code, body: $(body_preview)"
      ;;
  esac

  login_payload=$(printf '{"email":"%s","password":"%s"}' "$SMOKE_EMAIL" "$SMOKE_PASSWORD")
  login_code="$(request_code POST "$BASE_URL/auth/login" "$login_payload")" || fail "login request failed"
  case "$login_code" in
    200)
      save_response_snippet "auth-login" "POST" "$BASE_URL/auth/login" "$login_code" "PASS"
      pass "login endpoint reachable (200)"
      if [ "$HAS_JQ" -eq 1 ]; then
        auth_token="$(jq -r '.session_token // empty' "$tmp_body" 2>/dev/null || true)"
      fi
      ;;
    401|403)
      save_response_snippet "auth-login" "POST" "$BASE_URL/auth/login" "$login_code" "PASS"
      pass "login endpoint reachable (auth semantics: $login_code)"
      ;;
    *)
      save_response_snippet "auth-login" "POST" "$BASE_URL/auth/login" "$login_code" "FAIL"
      fail "login endpoint unexpected status: $login_code, body: $(body_preview)"
      ;;
  esac
else
  probe_payload='{"email":"invalid-email","password":"short"}'
  register_code="$(request_code POST "$BASE_URL/auth/register" "$probe_payload")" || fail "register reachability probe failed"
  case "$register_code" in
    422|400|409)
      save_response_snippet "auth-register-probe" "POST" "$BASE_URL/auth/register" "$register_code" "PASS"
      pass "register endpoint reachable (validation semantics: $register_code)"
      ;;
    *)
      save_response_snippet "auth-register-probe" "POST" "$BASE_URL/auth/register" "$register_code" "FAIL"
      fail "register reachability probe unexpected status: $register_code, body: $(body_preview)"
      ;;
  esac

  login_code="$(request_code POST "$BASE_URL/auth/login" "$probe_payload")" || fail "login reachability probe failed"
  case "$login_code" in
    422|400|401|403)
      save_response_snippet "auth-login-probe" "POST" "$BASE_URL/auth/login" "$login_code" "PASS"
      pass "login endpoint reachable (validation/auth semantics: $login_code)"
      ;;
    *)
      save_response_snippet "auth-login-probe" "POST" "$BASE_URL/auth/login" "$login_code" "FAIL"
      fail "login reachability probe unexpected status: $login_code, body: $(body_preview)"
      ;;
  esac
fi

# 3) Mailbox connect endpoint reachable
mailbox_code="$(request_code GET "$BASE_URL/mailbox-connect/gmail/connect" "" "$auth_token")" || fail "mailbox connect request failed"
case "$mailbox_code" in
  200)
    save_response_snippet "mailbox-connect" "GET" "$BASE_URL/mailbox-connect/gmail/connect" "$mailbox_code" "PASS"
    pass "mailbox connect endpoint reachable (authenticated success: 200)"
    ;;
  401|403|422)
    save_response_snippet "mailbox-connect" "GET" "$BASE_URL/mailbox-connect/gmail/connect" "$mailbox_code" "PASS"
    pass "mailbox connect endpoint reachable (auth-required semantics: $mailbox_code)"
    ;;
  *)
    save_response_snippet "mailbox-connect" "GET" "$BASE_URL/mailbox-connect/gmail/connect" "$mailbox_code" "FAIL"
    fail "mailbox connect endpoint unexpected status: $mailbox_code, body: $(body_preview)"
    ;;
esac

# 4) Optional webhook route presence check
if [ "$CHECK_WEBHOOKS" = "1" ]; then
  webhook_code="$(request_code POST "$BASE_URL/webhooks/gmail" "{}")" || fail "webhook route probe failed"
  case "$webhook_code" in
    200|202|400|401|403|422)
      save_response_snippet "webhooks-gmail" "POST" "$BASE_URL/webhooks/gmail" "$webhook_code" "PASS"
      pass "webhooks route present (/webhooks/gmail) with expected semantics: $webhook_code"
      ;;
    404|405)
      save_response_snippet "webhooks-gmail" "POST" "$BASE_URL/webhooks/gmail" "$webhook_code" "FAIL"
      fail "webhooks route likely missing or method mismatch: $webhook_code, body: $(body_preview)"
      ;;
    *)
      save_response_snippet "webhooks-gmail" "POST" "$BASE_URL/webhooks/gmail" "$webhook_code" "FAIL"
      fail "webhooks route unexpected status: $webhook_code, body: $(body_preview)"
      ;;
  esac
else
  save_response_snippet "webhooks-gmail" "POST" "$BASE_URL/webhooks/gmail" "SKIP" "SKIP"
  echo "SKIP: webhook route presence check disabled (CHECK_WEBHOOKS=$CHECK_WEBHOOKS)"
fi

echo "All Day-0 sandbox smoke checks passed."
