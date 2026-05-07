#!/usr/bin/env bash
# setup_ngrok_dev.sh — Start an ngrok tunnel for local Gmail webhook development.
#
# What it does:
#   1. Checks ngrok is installed.
#   2. Starts ngrok on port 8000 in the background.
#   3. Polls the ngrok local API until the public URL is available.
#   4. Prints the WEBHOOK_BASE_URL value to copy into .env.
#   5. Calls the backend /dev/ingest endpoint instructions and triggers
#      Gmail watch renewal via the /auth/watch endpoint if the backend is up.
#
# Usage:
#   ./scripts/setup_ngrok_dev.sh
#
# Prerequisites:
#   - ngrok installed and authenticated (ngrok config add-authtoken <token>)
#   - Backend running on http://localhost:8000 (make dev or docker compose up api)

set -euo pipefail

BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
NGROK_PORT="${NGROK_PORT:-8000}"
NGROK_API="${NGROK_API_URL:-http://localhost:4040}"
NGROK_TUNNEL_WAIT_SECS="${NGROK_TUNNEL_WAIT_SECS:-15}"

log()  { echo "[ngrok-dev] $*"; }
step() { echo; echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# 1. Check ngrok is installed
# ---------------------------------------------------------------------------
step "Checking for ngrok"
if ! command -v ngrok &>/dev/null; then
  echo "ERROR: ngrok is not installed or not on PATH."
  echo "Install it: https://ngrok.com/download"
  echo "Then authenticate: ngrok config add-authtoken <your-auth-token>"
  exit 1
fi
log "ngrok found at: $(command -v ngrok)"

# ---------------------------------------------------------------------------
# 2. Kill any existing ngrok process on the same port to ensure a clean state
# ---------------------------------------------------------------------------
if pgrep -f "ngrok http ${NGROK_PORT}" &>/dev/null; then
  log "Stopping existing ngrok tunnel on port ${NGROK_PORT}..."
  pkill -f "ngrok http ${NGROK_PORT}" || true
  sleep 1
fi

# ---------------------------------------------------------------------------
# 3. Start ngrok in the background
# ---------------------------------------------------------------------------
step "Starting ngrok tunnel on port ${NGROK_PORT}"
ngrok http "${NGROK_PORT}" --log=stdout > /tmp/ngrok-inbox-dev.log 2>&1 &
NGROK_PID=$!
log "ngrok started (PID ${NGROK_PID}). Log: /tmp/ngrok-inbox-dev.log"

# ---------------------------------------------------------------------------
# 4. Poll ngrok local API for the public URL
# ---------------------------------------------------------------------------
step "Waiting for ngrok tunnel to become available (up to ${NGROK_TUNNEL_WAIT_SECS}s)"
PUBLIC_URL=""
ELAPSED=0
while [[ -z "${PUBLIC_URL}" && ${ELAPSED} -lt ${NGROK_TUNNEL_WAIT_SECS} ]]; do
  sleep 1
  ELAPSED=$((ELAPSED + 1))
  # ngrok exposes tunnel metadata on its local API
  PUBLIC_URL=$(curl -s "${NGROK_API}/api/tunnels" 2>/dev/null \
    | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    tunnels = data.get('tunnels', [])
    for t in tunnels:
        if t.get('proto') == 'https':
            print(t['public_url'])
            break
except Exception:
    pass
" || true)
done

if [[ -z "${PUBLIC_URL}" ]]; then
  echo "ERROR: ngrok tunnel did not start within ${NGROK_TUNNEL_WAIT_SECS}s."
  echo "Check logs: /tmp/ngrok-inbox-dev.log"
  echo "Ensure you have authenticated ngrok: ngrok config add-authtoken <token>"
  kill "${NGROK_PID}" 2>/dev/null || true
  exit 1
fi

log "Tunnel active: ${PUBLIC_URL}"

# ---------------------------------------------------------------------------
# 5. Print env var to copy
# ---------------------------------------------------------------------------
step "Update your backend .env"
echo
echo "  WEBHOOK_BASE_URL=${PUBLIC_URL}"
echo
echo "Copy the line above into backend/.env then restart the backend."
echo "The Pub/Sub subscription push endpoint will be:"
echo "  ${PUBLIC_URL}/webhooks/gmail"

# ---------------------------------------------------------------------------
# 6. Optionally update the Pub/Sub subscription if PROJECT_ID is set
# ---------------------------------------------------------------------------
if [[ -n "${PROJECT_ID:-}" ]]; then
  step "Updating Pub/Sub subscription push endpoint"
  if gcloud pubsub subscriptions modify-push-config inbox-chief-of-staff-push \
       --project="${PROJECT_ID}" \
       --push-endpoint="${PUBLIC_URL}/webhooks/gmail" \
       --quiet 2>/dev/null; then
    log "Pub/Sub subscription updated."
  else
    log "Could not update Pub/Sub subscription (gcloud may not be configured)."
    log "Run manually:"
    log "  gcloud pubsub subscriptions modify-push-config inbox-chief-of-staff-push \\"
    log "    --push-endpoint=${PUBLIC_URL}/webhooks/gmail"
  fi
else
  log "PROJECT_ID not set — skipping automatic Pub/Sub update."
  log "To update manually, set PROJECT_ID and re-run, or run:"
  log "  gcloud pubsub subscriptions modify-push-config inbox-chief-of-staff-push \\"
  log "    --push-endpoint=${PUBLIC_URL}/webhooks/gmail"
fi

# ---------------------------------------------------------------------------
# 7. Check if backend is up and print Gmail watch renewal instructions
# ---------------------------------------------------------------------------
step "Gmail watch renewal"
if curl -sf "${BACKEND_URL}/health" &>/dev/null; then
  log "Backend is reachable at ${BACKEND_URL}."
  log "To register/renew the Gmail push watch, call:"
  log "  POST ${BACKEND_URL}/auth/watch"
  log "  (You must be authenticated — use the browser OAuth flow first.)"
else
  log "Backend is not reachable at ${BACKEND_URL}."
  log "Start it with: make dev   OR   docker compose up api"
  log "Then call: POST ${BACKEND_URL}/auth/watch  to register the Gmail watch."
fi

echo
log "ngrok is running in the background (PID ${NGROK_PID})."
log "To stop it: kill ${NGROK_PID}   OR   pkill -f 'ngrok http ${NGROK_PORT}'"
