#!/usr/bin/env bash
# provision_gcp.sh — Idempotently provisions all GCP resources for Inbox Chief of Staff.
#
# Usage:
#   PROJECT_ID=inbox-chief-of-staff-494719 REGION=us-central1 ./scripts/provision_gcp.sh
#
# Required env vars (with defaults):
#   PROJECT_ID  — GCP project ID  (default: inbox-chief-of-staff-494719)
#   REGION      — GCP region       (default: us-central1)
#   WEBHOOK_BASE_URL — Publicly reachable URL of the backend (default: placeholder)
#                      Format: https://your-cloud-run-service-url
#
# The script is safe to re-run; every create step checks for prior existence first.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ID="${PROJECT_ID:-inbox-chief-of-staff-494719}"
REGION="${REGION:-us-central1}"
WEBHOOK_BASE_URL="${WEBHOOK_BASE_URL:-https://YOUR_CLOUD_RUN_URL_HERE}"

TOPIC_NAME="inbox-chief-of-staff"
SUBSCRIPTION_NAME="inbox-chief-of-staff-push"
# The Gmail service account that Google uses to publish Pub/Sub messages on behalf of the user.
GMAIL_SA="gmail-api-push@system.gserviceaccount.com"

TASKS_QUEUE="inbox-chief-of-staff-tasks"
GCS_BUCKET="inbox-chief-of-staff-artifacts-${PROJECT_ID}"
SQL_INSTANCE="inbox-chief-of-staff-db"
SQL_TIER="db-f1-micro"  # Suitable for dev/staging; upgrade for production.
SQL_VERSION="POSTGRES_15"

WEBHOOK_PATH="/webhooks/gmail"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[provision] $*"; }
step() { echo; echo "=== $* ==="; }

# ---------------------------------------------------------------------------
# 0. Set active project
# ---------------------------------------------------------------------------
step "Setting active project to ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" --quiet

# ---------------------------------------------------------------------------
# 1. Enable required APIs
# ---------------------------------------------------------------------------
step "Enabling required GCP APIs"
APIS=(
  gmail.googleapis.com
  pubsub.googleapis.com
  run.googleapis.com
  sqladmin.googleapis.com
  cloudtasks.googleapis.com
  storage.googleapis.com
)
gcloud services enable "${APIS[@]}" --project="${PROJECT_ID}" --quiet
log "APIs enabled."

# ---------------------------------------------------------------------------
# 2. Create Pub/Sub topic (idempotent)
# ---------------------------------------------------------------------------
step "Creating Pub/Sub topic: ${TOPIC_NAME}"
if gcloud pubsub topics describe "${TOPIC_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
  log "Topic already exists — skipping."
else
  gcloud pubsub topics create "${TOPIC_NAME}" \
    --project="${PROJECT_ID}" \
    --quiet
  log "Topic created."
fi

# ---------------------------------------------------------------------------
# 3. Grant Gmail service account publish permission on the topic
# ---------------------------------------------------------------------------
step "Granting pubsub.publisher role to Gmail service account"
gcloud pubsub topics add-iam-policy-binding "${TOPIC_NAME}" \
  --project="${PROJECT_ID}" \
  --member="serviceAccount:${GMAIL_SA}" \
  --role="roles/pubsub.publisher" \
  --quiet
log "IAM binding applied (add-iam-policy-binding is idempotent)."

# ---------------------------------------------------------------------------
# 4. Create Pub/Sub push subscription (idempotent)
# ---------------------------------------------------------------------------
step "Creating Pub/Sub push subscription: ${SUBSCRIPTION_NAME}"
PUSH_ENDPOINT="${WEBHOOK_BASE_URL}${WEBHOOK_PATH}"
if gcloud pubsub subscriptions describe "${SUBSCRIPTION_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
  log "Subscription already exists — updating push endpoint to ${PUSH_ENDPOINT}."
  gcloud pubsub subscriptions modify-push-config "${SUBSCRIPTION_NAME}" \
    --project="${PROJECT_ID}" \
    --push-endpoint="${PUSH_ENDPOINT}" \
    --quiet
else
  gcloud pubsub subscriptions create "${SUBSCRIPTION_NAME}" \
    --project="${PROJECT_ID}" \
    --topic="${TOPIC_NAME}" \
    --push-endpoint="${PUSH_ENDPOINT}" \
    --ack-deadline=30 \
    --message-retention-duration=1d \
    --quiet
  log "Subscription created."
fi

# ---------------------------------------------------------------------------
# 5. Create Cloud Tasks queue (idempotent)
# ---------------------------------------------------------------------------
step "Creating Cloud Tasks queue: ${TASKS_QUEUE}"
if gcloud tasks queues describe "${TASKS_QUEUE}" \
     --location="${REGION}" \
     --project="${PROJECT_ID}" &>/dev/null; then
  log "Queue already exists — skipping."
else
  gcloud tasks queues create "${TASKS_QUEUE}" \
    --location="${REGION}" \
    --project="${PROJECT_ID}" \
    --max-concurrent-dispatches=20 \
    --max-attempts=5 \
    --quiet
  log "Queue created."
fi

# ---------------------------------------------------------------------------
# 6. Create GCS bucket (idempotent)
# ---------------------------------------------------------------------------
step "Creating GCS bucket: gs://${GCS_BUCKET}"
if gsutil ls -b "gs://${GCS_BUCKET}" &>/dev/null; then
  log "Bucket already exists — skipping."
else
  gcloud storage buckets create "gs://${GCS_BUCKET}" \
    --project="${PROJECT_ID}" \
    --location="${REGION}" \
    --uniform-bucket-level-access \
    --quiet
  log "Bucket created."
fi

# ---------------------------------------------------------------------------
# 7. Create Cloud SQL Postgres 15 instance (idempotent — slowest step ~5 min)
# ---------------------------------------------------------------------------
step "Creating Cloud SQL instance: ${SQL_INSTANCE} (this may take several minutes)"
if gcloud sql instances describe "${SQL_INSTANCE}" --project="${PROJECT_ID}" &>/dev/null; then
  log "Cloud SQL instance already exists — skipping creation."
else
  gcloud sql instances create "${SQL_INSTANCE}" \
    --project="${PROJECT_ID}" \
    --database-version="${SQL_VERSION}" \
    --tier="${SQL_TIER}" \
    --region="${REGION}" \
    --database-flags=cloudsql.enable_pgvector=on \
    --storage-auto-increase \
    --backup-start-time=03:00 \
    --quiet
  log "Cloud SQL instance created."
fi

# Create the application database (idempotent)
log "Ensuring database 'inbox_chief' exists on the instance..."
if gcloud sql databases describe inbox_chief \
     --instance="${SQL_INSTANCE}" \
     --project="${PROJECT_ID}" &>/dev/null; then
  log "Database already exists — skipping."
else
  gcloud sql databases create inbox_chief \
    --instance="${SQL_INSTANCE}" \
    --project="${PROJECT_ID}" \
    --quiet
  log "Database created."
fi

# Retrieve the Cloud SQL connection name for use in DATABASE_URL / Cloud Run.
SQL_CONNECTION_NAME=$(gcloud sql instances describe "${SQL_INSTANCE}" \
  --project="${PROJECT_ID}" \
  --format="value(connectionName)")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
step "Provisioning complete — copy these values into your .env / .env.production"
cat <<EOF

# ---- Pub/Sub ---------------------------------------------------------------
PUBSUB_TOPIC=projects/${PROJECT_ID}/topics/${TOPIC_NAME}

# ---- Cloud Run webhook URL (update after first deploy) ---------------------
WEBHOOK_BASE_URL=${WEBHOOK_BASE_URL}

# ---- Cloud Tasks -----------------------------------------------------------
QUEUE_URL=https://cloudtasks.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/queues/${TASKS_QUEUE}

# ---- Object storage --------------------------------------------------------
OBJECT_STORAGE_BUCKET=${GCS_BUCKET}
OBJECT_STORAGE_REGION=${REGION}

# ---- Cloud SQL (Cloud Run connects via unix socket through Cloud SQL proxy) -
# Replace DB_PASSWORD with the password you set for the postgres user.
DATABASE_URL=postgresql+asyncpg://postgres:DB_PASSWORD@/inbox_chief?host=/cloudsql/${SQL_CONNECTION_NAME}
# Cloud Run --add-cloudsql-instances flag value:
CLOUD_SQL_CONNECTION_NAME=${SQL_CONNECTION_NAME}

EOF
log "Done."
