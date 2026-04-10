# Deep-link contract: landing → Streamlit

Base: `NEXT_PUBLIC_STREAMLIT_BASE_URL` (no trailing slash).

| Param  | Values                    | Effect                                      |
|--------|---------------------------|---------------------------------------------|
| `role` | `admin`, `user`, `viewer` | Initial sidebar role (non-prod; see RBAC). |
| `page` | `prospecting`, `map`      | Initial Navigate page.                      |

Examples: `?role=user&page=prospecting`, `?role=admin&page=map`.

**Consumer:** `rula-gtm-agent/app.py` — `_apply_landing_query_params` reads `st.query_params`, re-applies when the `(page, role)` pair **changes** (same browser session), and clears sidebar widget state so **Navigate** / **Your role** match the new link. See `rula-gtm-agent/README.md` (Landing page deep links).
