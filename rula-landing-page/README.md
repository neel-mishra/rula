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

Set this in **Vercel → Project → Settings → Environment Variables** for Production and Preview.

## Deep links

Query parameters passed to Streamlit are documented in [docs/deep-link-contract.md](./docs/deep-link-contract.md). Streamlit behavior and RBAC are documented in [docs/streamlit-preservation.md](./docs/streamlit-preservation.md).

## Deploy on Vercel

1. Import this GitHub repository in Vercel.
2. Set **Root Directory** to `rula-landing-page`.
3. Add `NEXT_PUBLIC_STREAMLIT_BASE_URL` pointing at your hosted Streamlit URL.
4. Deploy.

## Security note

The Streamlit role selector is a **demo affordance** in non-production environments. For internet-facing deployments, use real authentication and server-side roles; see `rula-gtm-agent/README.md`.
