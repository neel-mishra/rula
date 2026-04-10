# Rula Revenue Intelligence — Landing (Vercel)

Hostfully-style landing page: pick **role** (Admin / User / Viewer), then launch **Prospecting** or **MAP Review** in the existing Streamlit app (`rula-gtm-agent`). **Insights** is not linked from this page; it remains available inside Streamlit for authorized roles.

## Prerequisites

- Node.js 20+ recommended
- Streamlit app running separately (local or hosted)

## Local development

```bash
cd rula-landing-page
cp .env.example .env.local
# Edit NEXT_PUBLIC_STREAMLIT_BASE_URL if needed (default http://localhost:8501)
npm install
npm run dev
```

In another terminal, from `rula-gtm-agent`:

```bash
streamlit run app.py
```

Open [http://localhost:3000](http://localhost:3000) for the landing page.

## Environment variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_STREAMLIT_BASE_URL` | Full origin of the Streamlit app, e.g. `https://your-app.streamlit.app` or `http://localhost:8501` |

**Local dev:** if unset, the app defaults to `http://localhost:8501` so tool links work without `.env.local`.

Set this in **Vercel → Project → Settings → Environment Variables** for Production and Preview (required there).

## Deep links

Query parameters passed to Streamlit are documented in [docs/deep-link-contract.md](./docs/deep-link-contract.md). Streamlit behavior and RBAC are documented in [docs/streamlit-preservation.md](./docs/streamlit-preservation.md).

## Deploy on Vercel

1. **Import** the GitHub repo (same monorepo as `rula-gtm-agent`).
2. **Root Directory:** `rula-landing-page` (required — do not use repo root).
3. **Environment variables** (Production and Preview):
   - `NEXT_PUBLIC_STREAMLIT_BASE_URL` = your Streamlit app **origin only**, e.g. `https://rula-gtm-agent.streamlit.app`  
   - **No trailing slash.** Use **https** so it matches your HTTPS landing.
4. **Deploy**, then open the Vercel URL → pick role → **Launch** → confirm the new tab opens Streamlit with `?role=…&page=…` in the address bar and the correct sidebar page.

### Linkage (already in code)

- The landing builds `https://<streamlit-host>/?role=<admin|user|viewer>&page=<prospecting|map>`.
- `rula-gtm-agent/app.py` applies those query params (`_apply_landing_query_params`) so **Navigate** and (in non-production) **Your role** match the landing choice.

If `NEXT_PUBLIC_STREAMLIT_BASE_URL` is missing on Vercel, launch links resolve to `#` until you set the variable and **redeploy** (Next bakes `NEXT_PUBLIC_*` at build time).

## Security note

The Streamlit role selector is a **demo affordance** in non-production environments. For internet-facing deployments, use real authentication and server-side roles; see `rula-gtm-agent/README.md`.
