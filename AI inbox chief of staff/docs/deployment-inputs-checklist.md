# Deployment inputs checklist (operator fill-in)

Use this when wiring **Vercel** + **Render** + **Google Cloud**. Do not commit completed forms with real secrets.

## Repository

- [ ] GitHub repo: `rula-gtm-agent`
- [ ] Branch for deploy: `___________________________`

## URLs (provider-first)

- [ ] Vercel app URL: `https://___________________________`
- [ ] Render API URL: `https://___________________________`
- [ ] (Later) Custom app domain: `___________________________`
- [ ] (Later) Custom API domain: `___________________________`

## Vercel environment variables

- [ ] `NEXT_PUBLIC_API_URL` = Render API URL (exact origin, no trailing slash on path)

## Render — shared (API + workers)

- [ ] `APP_ENV` = `dev` / `staging` / `prod` (pick one; drives validation in `core/config.py`)
- [ ] `APP_SECRET_KEY` (32+ characters)
- [ ] `DATABASE_URL` (`postgresql+asyncpg://...` from Render Postgres)
- [ ] `REDIS_URL` (from Render Redis)
- [ ] `CORS_ALLOWED_ORIGINS` = Vercel app origin(s), comma-separated
- [ ] `CORS_ALLOW_VERCEL_PREVIEW` = `true` / `false`
- [ ] `GOOGLE_CLIENT_ID`
- [ ] `GOOGLE_CLIENT_SECRET`
- [ ] `GOOGLE_REDIRECT_URI` = `https://<render-api>/mailbox-connect/gmail/callback`
- [ ] `GMAIL_WEBHOOK_TOPIC`
- [ ] `GMAIL_WEBHOOK_SECRET`
- [ ] `TOKEN_ENCRYPTION_KEY` (+ `KMS_KEY_ARN` if required for chosen `APP_ENV`)
- [ ] `ANTHROPIC_API_KEY`
- [ ] `OPENAI_API_KEY`
- [ ] `QUEUE_BACKEND` = `redis_streams` (typical for Render)
- [ ] `AWS_ACCOUNT_ID` and any other keys required by `Settings.validate_for_environment()` for your `APP_ENV`
- [ ] Optional SES/S3 keys if testing briefs and audit export end-to-end

## Google Cloud Console

- [ ] OAuth client IDs match Render env
- [ ] Authorized redirect URI includes `GOOGLE_REDIRECT_URI` above
- [ ] Pub/Sub push endpoint: `https://<render-api>/webhooks/gmail`

## Test accounts

- [ ] Gmail user for mailbox connect: `___________________________`
- [ ] Sender mailbox for test messages: `___________________________`

## Sign-off

- [ ] Health check OK
- [ ] Login + Gmail connect OK
- [ ] Test email → ingest visible in product

**Operator:** ___________________________ **Date:** ___________________________
