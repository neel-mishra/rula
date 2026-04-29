# Deploying Inbox Chief of Staff: Vercel (frontend) + Render (API + workers)

Monorepo layout: connect both platforms to the **`rula-gtm-agent`** GitHub repo.

| Layer | Platform | Root directory in repo |
|--------|----------|-------------------------|
| Next.js app | Vercel | `AI inbox chief of staff/frontend/app` |
| FastAPI + workers | Render | `AI inbox chief of staff` |

**Webhook rule:** Gmail Pub/Sub push must call the **API** (Render), not Vercel:

- Push URL: `https://<render-api-host>/webhooks/gmail`

**OAuth rule:** `GOOGLE_REDIRECT_URI` must be the **API** callback URL registered in Google Cloud:

- `https://<render-api-host>/mailbox-connect/gmail/callback`

The SPA uses `NEXT_PUBLIC_API_URL` to call the API ([`frontend/app/src/lib/api.ts`](../frontend/app/src/lib/api.ts)).

---

## 1. Prerequisites

- Code merged on the default branch (e.g. `main`) in `rula-gtm-agent`.
- Render: create **PostgreSQL** and **Redis** (managed). Add buckets/SSE later if you enable full SES/S3 features.
- Gather secrets: see [deployment-inputs-checklist.md](deployment-inputs-checklist.md).

---

## 2. Vercel (frontend)

1. **New Project** → import `rula-gtm-agent`.
2. **Root Directory:** `AI inbox chief of staff/frontend/app`.
3. **Framework Preset:** Next.js (auto).
4. **Build:** `npm ci` (or default install) + `npm run build`.
5. **Environment variables**
   - `NEXT_PUBLIC_API_URL` = `https://<your-render-api-service>.onrender.com` (or custom API domain).

After the first API deploy, set this variable and **Redeploy** so the browser targets the live API.

---

## 3. Render (API)

1. **New** → **Web Service** → connect `rula-gtm-agent`.
2. **Root Directory:** `AI inbox chief of staff`.
3. **Runtime:** Python 3.11.
4. **Build command**

   ```bash
   pip install poetry==1.8.2 && poetry config virtualenvs.create false && poetry install --no-root --without dev
   ```

5. **Start command**

   ```bash
   uvicorn api.main:app --host 0.0.0.0 --port $PORT
   ```

6. **Health check path:** `/health/`

7. **Environment variables** (minimum for hosted MVP; align with [`.env.example`](../.env.example)):

   - `APP_ENV` — use `staging` for first hosted cut, or `prod` when ready for stricter validation.
   - `APP_SECRET_KEY` (32+ chars)
   - `DATABASE_URL` — Render Postgres internal URL; use `postgresql+asyncpg://...` adapter string.
   - `REDIS_URL` — Render Redis URL (with password).
   - `CORS_ALLOWED_ORIGINS` — your Vercel production URL, e.g. `https://your-app.vercel.app`  
     Optionally comma-separate multiple origins.
   - `CORS_ALLOW_VERCEL_PREVIEW` — `true` during MVP if you need **all** `https://*.vercel.app` previews; set `false` for strict production.
   - Google: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` (must match API callback URL).
   - `GMAIL_WEBHOOK_TOPIC`, `GMAIL_WEBHOOK_SECRET`
   - `TOKEN_ENCRYPTION_KEY` (and `KMS_KEY_ARN` if required for your `APP_ENV` validation — see `core/config.py`).
   - `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
   - `QUEUE_BACKEND=redis_streams` (recommended with Render Redis)
   - `AWS_ACCOUNT_ID` and other keys if `validate_for_environment` requires them for your chosen `APP_ENV`.

8. Run DB migrations (one-off job or shell on Render):

   ```bash
   alembic upgrade head
   ```

   (Requires `alembic.ini` / `migrations/` as in repo; if migrations are missing, add them before production.)

---

## 4. Render (ingest worker)

Duplicate the Python **build** from the API service.

**Start command:**

```bash
python -m workers.ingest_worker
```

Use the **same** environment variables as the API (especially `DATABASE_URL`, `REDIS_URL`, queue settings).

---

## 5. Render (scheduler)

Use a **Cron Job** or a long-running worker that invokes the scheduler on an interval.

**One-shot scheduler run (cron-friendly):**

```bash
python -m workers.scheduler
```

Example schedule: hourly `0 * * * *` (tune for watch renewal / brief windows).

---

## 6. Google Cloud (OAuth + Gmail push)

1. **OAuth consent** — sensitive scopes may require verification (see [launch-blockers-execution.md](launch-blockers-execution.md)).
2. **Authorized redirect URIs** — add  
   `https://<render-api-host>/mailbox-connect/gmail/callback`
3. **Pub/Sub** — push subscription endpoint  
   `https://<render-api-host>/webhooks/gmail`  
   Align signing secret with `GMAIL_WEBHOOK_SECRET`.

---

## 7. Verification

1. `GET https://<render-api>/health/` → `200`.
2. Open Vercel app → register/login → session persists.
3. **Connect Gmail** — completes without redirect mismatch errors.
4. Send a test email → webhook accepted → ingest worker processes (check logs / DB / UI).

---

## 8. Rollback

- **Vercel:** Promote previous deployment or revert git commit and redeploy.
- **Render:** Dashboard **Manual Deploy** → select previous good commit; fix env vars if mis-set.

---

## 9. Optional: `render.yaml` blueprint

A starter blueprint lives at [`render.yaml`](../render.yaml). Adjust service names, regions, and link Postgres/Redis in the Render dashboard if not declared in the file.

---

## Troubleshooting (quick)

| Symptom | Check |
|--------|--------|
| Browser “CORS” / failed fetch | `CORS_ALLOWED_ORIGINS` includes exact Vercel URL; trailing slash usually omitted; try `CORS_ALLOW_VERCEL_PREVIEW=true` for previews. |
| OAuth `redirect_uri_mismatch` | Google Console redirect must match `GOOGLE_REDIRECT_URI` on API. |
| Webhook never hits API | Pub/Sub push URL must be Render API, not Vercel; HTTPS required. |
| 401 on API | `Authorization: Bearer` token; same `APP_SECRET_KEY` across deploys or re-login. |
| Queue never drains | Ingest worker service running; `REDIS_URL` + `QUEUE_BACKEND` consistent with API. |
