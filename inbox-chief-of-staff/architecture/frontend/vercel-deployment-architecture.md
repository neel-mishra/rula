# Vercel Deployment Architecture

**Project:** Inbox Chief of Staff  
**Phase:** Prototype  
**Last updated:** 2026-04-30

---

## Overview

The frontend is deployed on Vercel. Every pull request receives an isolated Preview deployment. The `main` branch deploys to Production only after passing the Phase Gate (CI + manual approval). Preview and Production environments are fully isolated — they point to separate backend services and separate databases.

---

## Environment Strategy

| Environment | Trigger | API target | Gmail data |
|---|---|---|---|
| `preview` | Every PR push | Staging backend (Cloud Run `staging`) | Test data only — no real Gmail accounts |
| `production` | Merge to `main` + Phase Gate approval | Production backend (Cloud Run `prod`) | Real Gmail data, live OAuth |

### Preview environment

- Vercel automatically creates a unique URL per PR (e.g., `inbox-pr-42.vercel.app`).
- All preview deployments share the same staging environment variables (configured once in Vercel project settings under "Preview" scope).
- Staging backend uses a separate Cloud SQL instance populated with anonymized/synthetic test data.
- Google OAuth in preview uses a dedicated test Google account (not a real user account). Real OAuth scopes are not exercised in preview.
- Preview deployments are automatically deleted when a PR is closed or merged.

### Production environment

- Deploys only from `main`.
- Vercel deploy is gated: requires passing CI and manual approval via Vercel's "Production deployment protection" setting.
- Production uses live Gmail OAuth and real user data.
- Production deployments are immutable; rollback is done by promoting a previous deployment in the Vercel dashboard (not by reverting commits).

---

## Required Environment Variables

All variables are set per-environment in the Vercel project dashboard (Project Settings → Environment Variables). Variables are scoped to `preview`, `production`, or both.

| Variable | Scope | Runtime visibility | Description |
|---|---|---|---|
| `NEXT_PUBLIC_API_BASE_URL` | preview + production | Client + server | Base URL of the backend REST API. Preview points to staging Cloud Run URL; production points to prod Cloud Run URL. |
| `NEXT_PUBLIC_APP_ENV` | preview + production | Client + server | `preview` or `production`. Used for conditional UI banners and analytics suppression in preview. |
| `GOOGLE_CLIENT_ID` | preview + production | Server-side only | Google OAuth client ID. Preview uses a dedicated test OAuth client; production uses the production OAuth client. |
| `GOOGLE_CLIENT_SECRET` | preview + production | Server-side only | Google OAuth client secret. Never exposed to the browser. |
| `SESSION_SECRET` | preview + production | Server-side only | Secret used to sign httpOnly session cookies. Must be at least 32 random bytes. Rotated independently per environment. |

**Variable hygiene rules:**
- Variables prefixed `NEXT_PUBLIC_` are bundled into the client JavaScript. Never put secrets in `NEXT_PUBLIC_` variables.
- `GOOGLE_CLIENT_SECRET` and `SESSION_SECRET` are marked "Sensitive" in Vercel (masked in logs, restricted from preview deployments if desired).
- No `.env` files are committed to the repository. The `.gitignore` must include `.env*`.

---

## Edge vs. Node.js Runtime

Vercel supports both Edge and Node.js runtimes per route. Assignment is explicit via the `runtime` export.

| Route | Runtime | Reason |
|---|---|---|
| `app/api/auth/[...nextauth]/route.ts` | Node.js | Requires `crypto` (session signing), HTTP-only cookie manipulation, and a session store — not available in Edge runtime. |
| `app/api/health/route.ts` | Node.js | Simple; co-located with other API routes for consistency. |
| `app/(app)/layout.tsx` and all page routes | Edge | Static shell; benefits from Edge's lower cold-start latency and global distribution. |
| `app/(auth)/callback/route.ts` | Node.js | OAuth code exchange uses `crypto` and Node.js `fetch` with full TLS; must run on Node.js. |

Runtime is declared per file:

```ts
// app/api/auth/[...nextauth]/route.ts
export const runtime = 'nodejs';

// app/(app)/layout.tsx
export const runtime = 'edge';
```

**Note on session store:** The session is stateless (JWT signed with `SESSION_SECRET`). No Redis or external session store is required in Prototype. If session invalidation on demand is needed (MVP), a Redis-backed session store would be introduced and the runtime would remain Node.js.

---

## Preview Environment Isolation

The following controls ensure preview deployments cannot access real user data or production systems.

### Backend isolation

- Preview `NEXT_PUBLIC_API_BASE_URL` points to the Cloud Run `staging` service.
- The staging Cloud Run service connects to a separate Cloud SQL instance (`inbox-staging` project).
- Staging Cloud SQL is populated with anonymized test fixtures — never a copy of production data.
- IAM roles for the staging service account do not grant access to production Cloud SQL, production Gmail OAuth clients, or production secrets.

### OAuth isolation

- Preview deployments use a dedicated Google Cloud project with its own OAuth 2.0 client credentials (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` for preview).
- Only a test Google account (owned by the engineering team) is authorized as a test user on the preview OAuth consent screen.
- The preview OAuth client has `http://localhost:3000` and `*.vercel.app` as authorized redirect URIs. The production OAuth client has only the production domain.
- This prevents any real user from accidentally authenticating through a preview URL.

### Environment banner

- When `NEXT_PUBLIC_APP_ENV=preview`, the app shell renders a persistent yellow banner at the top: "Preview environment — test data only, no real email."
- This prevents testers from confusing preview with production.

---

## Branch Protection and Deployment Gates

### main branch protection (GitHub)

Configured in GitHub repository settings:

- Require pull request before merging (no direct pushes to `main`).
- Require at least 1 approving review.
- Require status checks to pass before merging:
  - `ci / lint` — ESLint + TypeScript type check
  - `ci / test` — unit and integration tests (Vitest)
  - `ci / lighthouse` — Lighthouse CI (see below)
- Do not allow bypassing the above settings (applies to admins).

### Lighthouse CI gate

Every Vercel preview deployment is tested with Lighthouse CI before the PR can be merged.

Required thresholds:

| Category | Minimum score |
|---|---|
| Performance | 90 |
| Accessibility | 90 |
| Best Practices | 85 |
| SEO | — (not enforced in Prototype) |

Lighthouse CI runs against the Vercel preview URL using the `treosh/lighthouse-ci-action` GitHub Action. The action posts scores as a commit status check. A failing Lighthouse score blocks PR merge.

Configuration file: `lighthouserc.json` at repo root.

```json
{
  "ci": {
    "collect": {
      "url": ["$LHCI_URL/inbox", "$LHCI_URL/drafts", "$LHCI_URL/brief"],
      "numberOfRuns": 3
    },
    "assert": {
      "assertions": {
        "categories:performance": ["error", { "minScore": 0.9 }],
        "categories:accessibility": ["error", { "minScore": 0.9 }],
        "categories:best-practices": ["error", { "minScore": 0.85 }]
      }
    },
    "upload": {
      "target": "temporary-public-storage"
    }
  }
}
```

`LHCI_URL` is injected by the GitHub Action from the Vercel preview deployment URL (available via `vercel-action` outputs).

### Production deployment protection

Configured in Vercel project settings:

- "Deployment Protection" set to "Required" for Production.
- At least one team member must manually approve the production deployment in the Vercel dashboard after CI passes.
- This approval step is the Phase Gate between Prototype milestones.

---

## CI Pipeline Summary

```
PR opened / pushed
        |
        v
GitHub Actions: ci.yml
  ├── lint          (ESLint, tsc --noEmit)
  ├── test          (Vitest unit + integration)
  └── [after Vercel preview deploy]
       └── lighthouse   (runs against preview URL)
        |
        v (all checks green + 1 approval)
Merge to main
        |
        v
Vercel: production deploy
        |
        v
Manual approval in Vercel dashboard (Phase Gate)
        |
        v
Production live
```

---

## Rollback Procedure

1. Open the Vercel dashboard → Deployments tab.
2. Find the last known-good production deployment.
3. Click "Promote to Production" on that deployment.
4. Vercel instantly routes production traffic to the previous build — no re-deploy required.

Do not use `git revert` + re-merge as the primary rollback mechanism. Vercel's instant promotion is faster and avoids touching the `main` branch history under incident pressure.

---

## Custom Domain and TLS

- Production domain: configured in Vercel project settings (e.g., `app.inboxchiefofstaff.com`).
- TLS: managed by Vercel (auto-renewed Let's Encrypt certificates).
- HSTS header added via `next.config.ts` headers configuration.
- Preview deployments use Vercel's default `*.vercel.app` subdomain — no custom domain in preview.

---

## Monitoring and Observability

| Signal | Tooling | Notes |
|---|---|---|
| Frontend errors | Vercel Runtime Logs + (MVP: Sentry) | In Prototype, errors are visible in Vercel logs; Sentry integration deferred to MVP |
| Performance | Lighthouse CI (per PR) | Score history visible in Lighthouse CI dashboard |
| Availability | Vercel built-in uptime checks | Alerts to engineering email on downtime |
| Deploy notifications | Vercel → Slack webhook | Posted to `#deploys` channel on successful preview and production deploys |
