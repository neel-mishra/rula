#!/usr/bin/env bash
# deploy_cloud_run.sh — Build and deploy the backend to Cloud Run.
#
# Usage:
#   PROJECT_ID=inbox-chief-of-staff-494719 \
#   REGION=us-central1 \
#   IMAGE_TAG=latest \
#   ./scripts/deploy_cloud_run.sh
#
# Prerequisites:
#   - gcloud CLI authenticated with permission to deploy Cloud Run services
#   - backend/.env.production exists (see backend/.env.example)
#   - Cloud SQL instance already provisioned (run provision_gcp.sh first)

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID="${PROJECT_ID:-inbox-chief-of-staff-494719}"
REGION="${REGION:-us-central1}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

SERVICE_NAME="inbox-chief-of-staff-api"
REPO="gcr.io/${PROJECT_ID}/${SERVICE_NAME}"
IMAGE="${REPO}:${IMAGE_TAG}"
ENV_FILE="${ENV_FILE:-backend/.env.production}"
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backend"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[deploy] $*"; }
step() { echo; echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# Validate inputs
# ---------------------------------------------------------------------------
step "Validating prerequisites"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "ERROR: ${ENV_FILE} not found."
  echo "Copy backend/.env.example to backend/.env.production and fill in all values."
  exit 1
fi

# Ensure CLOUD_SQL_CONNECTION_NAME is set — required to wire the proxy sidecar.
CLOUD_SQL_CONNECTION_NAME="${CLOUD_SQL_CONNECTION_NAME:-}"
if [[ -z "${CLOUD_SQL_CONNECTION_NAME}" ]]; then
  # Attempt to read from the env file as a fallback.
  CLOUD_SQL_CONNECTION_NAME=$(grep -E '^CLOUD_SQL_CONNECTION_NAME=' "${ENV_FILE}" \
    | cut -d= -f2- | tr -d '"' || true)
fi
if [[ -z "${CLOUD_SQL_CONNECTION_NAME}" ]]; then
  echo "ERROR: CLOUD_SQL_CONNECTION_NAME is not set."
  echo "Run provision_gcp.sh first and copy the value into ${ENV_FILE}."
  exit 1
fi

log "Project:  ${PROJECT_ID}"
log "Region:   ${REGION}"
log "Image:    ${IMAGE}"
log "Env file: ${ENV_FILE}"
log "Cloud SQL: ${CLOUD_SQL_CONNECTION_NAME}"

# ---------------------------------------------------------------------------
# Build image via Cloud Build (no local Docker daemon required)
# ---------------------------------------------------------------------------
step "Submitting Cloud Build for ${IMAGE}"
gcloud builds submit "${BACKEND_DIR}" \
  --project="${PROJECT_ID}" \
  --tag="${IMAGE}" \
  --quiet

log "Image built and pushed to ${IMAGE}."

# ---------------------------------------------------------------------------
# Parse .env.production into --set-env-vars format
# ---------------------------------------------------------------------------
step "Reading env vars from ${ENV_FILE}"
# Strip blank lines and comments; join KEY=VALUE pairs with commas.
# Values containing commas must be passed via --set-env-vars-from-file or
# Secret Manager — this loader handles the common case of simple scalar values.
ENV_VARS=""
while IFS= read -r line || [[ -n "${line}" ]]; do
  # Skip blank lines and comments
  [[ -z "${line}" || "${line}" =~ ^[[:space:]]*# ]] && continue
  # Skip CLOUD_SQL_CONNECTION_NAME — it's used as a flag, not an env var
  [[ "${line}" =~ ^CLOUD_SQL_CONNECTION_NAME= ]] && continue
  # Append to comma-separated list, quoting value
  key="${line%%=*}"
  val="${line#*=}"
  # Remove surrounding quotes if present
  val="${val%\"}"
  val="${val#\"}"
  if [[ -n "${ENV_VARS}" ]]; then
    ENV_VARS="${ENV_VARS},${key}=${val}"
  else
    ENV_VARS="${key}=${val}"
  fi
done < "${ENV_FILE}"

# ---------------------------------------------------------------------------
# Deploy to Cloud Run
# ---------------------------------------------------------------------------
step "Deploying ${SERVICE_NAME} to Cloud Run in ${REGION}"
gcloud run deploy "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=10 \
  --memory=1Gi \
  --cpu=1 \
  --concurrency=80 \
  --timeout=60 \
  --add-cloudsql-instances="${CLOUD_SQL_CONNECTION_NAME}" \
  --set-env-vars="${ENV_VARS}" \
  --quiet

# ---------------------------------------------------------------------------
# Print deployed URL
# ---------------------------------------------------------------------------
step "Deployment complete"
SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" \
  --project="${PROJECT_ID}" \
  --region="${REGION}" \
  --format="value(status.url)")

log "Service URL: ${SERVICE_URL}"
echo
echo "Next steps:"
echo "  1. Copy the URL above into WEBHOOK_BASE_URL in ${ENV_FILE}."
echo "  2. Update the Pub/Sub push subscription endpoint:"
echo "       gcloud pubsub subscriptions modify-push-config inbox-chief-of-staff-push \\"
echo "         --push-endpoint=${SERVICE_URL}/webhooks/gmail"
echo "  3. Trigger Gmail watch renewal via the /auth/watch endpoint or startup logic."
